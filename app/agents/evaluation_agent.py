"""Evaluation agent implementation."""

from __future__ import annotations

import json

from app.config import Settings, get_settings
from app.database import update_application
from app.observability import traced
from app.state import ApplicationState
from app.tools.load_rubric import load_rubric_tool, validate_rubric_payload
from app.tools.ollama import OllamaError, generate_json_response
from app.tools.score_rubric import score_against_rubric_tool
from app.tools.validate_evaluation import parse_evaluation_narrative


def _load_rubric_from_state_or_disk(
    state: ApplicationState, *, default_rubric_path: str
) -> dict[str, object]:
    """Resolve the rubric payload from state override or default disk path."""
    rubric = state.get("rubric")
    if rubric is None:
        return dict(load_rubric_tool.invoke({"path": default_rubric_path}))
    if not isinstance(rubric, dict):
        raise ValueError("rubric must be a dictionary when provided in state")
    return validate_rubric_payload(rubric).model_dump()


def _build_reasoning_prompt(
    *, extracted_json: dict[str, object], scoring_result: dict[str, object]
) -> str:
    """Create the structured prompt used for the evaluation narrative model."""
    return (
        "You are the Evaluation Agent for a recruitment analysis workflow.\n"
        "Use the extracted applicant data and deterministic scoring breakdown to produce a concise, "
        "professional evaluation narrative.\n"
        "Return JSON only with exactly these keys:\n"
        "{\n"
        '  "overall_summary": string,\n'
        '  "strengths": [string, ...],\n'
        '  "gaps": [string, ...]\n'
        "}\n\n"
        "EXTRACTED_JSON:\n"
        f"{json.dumps(extracted_json, indent=2, ensure_ascii=False)}\n\n"
        "SCORING_BREAKDOWN:\n"
        f"{json.dumps(scoring_result, indent=2, ensure_ascii=False)}"
    )


def _format_breakdown(scoring_result: dict[str, object]) -> list[str]:
    """Format the criterion breakdown as markdown-style bullet lines."""
    breakdown = scoring_result.get("criterion_breakdown", [])
    if not isinstance(breakdown, list):
        return []

    lines: list[str] = []
    for criterion in breakdown:
        if not isinstance(criterion, dict):
            continue
        name = str(criterion.get("name", "Unknown Criterion"))
        weight = float(criterion.get("weight", 0.0)) * 100.0
        score = float(criterion.get("score", 0.0))
        reasoning = str(criterion.get("reasoning", ""))
        lines.append(f"- {name} ({weight:.0f}%): {score:.2f}/100. {reasoning}")
    return lines


def _build_fallback_reasoning(scoring_result: dict[str, object]) -> str:
    """Create a deterministic reasoning summary when model generation is unavailable."""
    breakdown = scoring_result.get("criterion_breakdown", [])
    breakdown_items = [item for item in breakdown if isinstance(item, dict)]
    total_score = float(scoring_result.get("total_score", 0.0))

    strengths: list[str] = []
    gaps: list[str] = []
    if breakdown_items:
        strongest = max(breakdown_items, key=lambda item: float(item.get("score", 0.0)))
        weakest = min(breakdown_items, key=lambda item: float(item.get("score", 0.0)))
        strengths.append(
            f"Strongest area: {strongest.get('name', 'Unknown')} "
            f"({float(strongest.get('score', 0.0)):.2f}/100)"
        )
        gaps.append(
            f"Main gap: {weakest.get('name', 'Unknown')} "
            f"({float(weakest.get('score', 0.0)):.2f}/100)"
        )

    lines = [
        f"Overall summary: Candidate received a weighted evaluation score of {total_score:.2f}/100.",
    ]
    if strengths:
        lines.append("Strengths:")
        lines.extend(f"- {item}" for item in strengths)
    if gaps:
        lines.append("Gaps:")
        lines.extend(f"- {item}" for item in gaps)
    lines.append("Criterion breakdown:")
    lines.extend(_format_breakdown(scoring_result))
    return "\n".join(lines)


def _generate_reasoning(
    *,
    extracted_json: dict[str, object],
    scoring_result: dict[str, object],
    settings: Settings,
) -> str:
    """Generate the narrative summary, falling back to deterministic text if needed."""
    try:
        raw_response = generate_json_response(
            base_url=settings.ollama_base_url,
            model=settings.evaluation_model,
            prompt=_build_reasoning_prompt(
                extracted_json=extracted_json, scoring_result=scoring_result
            ),
            temperature=0.1,
            top_p=0.2,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
        narrative = parse_evaluation_narrative(raw_response)

        lines = [f"Overall summary: {narrative.overall_summary}"]
        if narrative.strengths:
            lines.append("Strengths:")
            lines.extend(f"- {item}" for item in narrative.strengths)
        if narrative.gaps:
            lines.append("Gaps:")
            lines.extend(f"- {item}" for item in narrative.gaps)
        lines.append("Criterion breakdown:")
        lines.extend(_format_breakdown(scoring_result))
        return "\n".join(lines)
    except (OllamaError, ValueError, TypeError):
        return _build_fallback_reasoning(scoring_result)


def evaluate_extracted_json(
    extracted_json: dict[str, object],
    *,
    rubric: dict[str, object] | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    """Run the evaluation logic without agent-state persistence.

    Args:
        extracted_json: Structured applicant data from the extraction stage.
        rubric: Optional rubric override; defaults to the configured rubric file.
        settings: Optional application settings override.

    Returns:
        The evaluation score, reasoning, and scoring metadata.

    Raises:
        ValueError: If the extracted data or rubric is invalid.

    Example:
        evaluate_extracted_json({"skills": ["Python"]})
    """
    runtime_settings = settings or get_settings()
    state: ApplicationState = {"rubric": rubric} if rubric is not None else {}
    resolved_rubric = _load_rubric_from_state_or_disk(
        state, default_rubric_path=runtime_settings.default_rubric_path
    )
    scoring_result = dict(
        score_against_rubric_tool.invoke(
            {"extracted_json": extracted_json, "rubric": resolved_rubric}
        )
    )
    evaluation_score = float(scoring_result["total_score"])
    evaluation_reasoning = _generate_reasoning(
        extracted_json=extracted_json,
        scoring_result=scoring_result,
        settings=runtime_settings,
    )
    return {
        "evaluation_score": evaluation_score,
        "evaluation_reasoning": evaluation_reasoning,
        "criterion_breakdown": scoring_result["criterion_breakdown"],
        "pass_threshold": scoring_result["pass_threshold"],
        "review_threshold": scoring_result["review_threshold"],
    }


@traced("evaluation_agent")
def evaluation_agent(state: ApplicationState) -> dict[str, object]:
    """Evaluate extracted candidate data against a rubric."""
    application_id = state.get("application_id")
    extracted_json = state.get("extracted_json")
    if not application_id or not extracted_json:
        raise ValueError("application_id and extracted_json are required in state")
    if not isinstance(extracted_json, dict):
        raise ValueError("extracted_json must be a dictionary")

    settings = get_settings()
    evaluation_result = evaluate_extracted_json(
        extracted_json,
        rubric=state.get("rubric") if isinstance(state.get("rubric"), dict) else None,
        settings=settings,
    )
    evaluation_score = float(evaluation_result["evaluation_score"])
    evaluation_reasoning = str(evaluation_result["evaluation_reasoning"])
    pass_threshold = float(evaluation_result["pass_threshold"])
    review_threshold = float(evaluation_result["review_threshold"])

    update_application(
        settings.db_path,
        application_id,
        {
            "status": "evaluated",
            "evaluation_score": evaluation_score,
            "evaluation_reasoning": evaluation_reasoning,
            "errors": state.get("errors", []),
        },
    )

    return {
        "status": "evaluated",
        "evaluation_score": evaluation_score,
        "evaluation_reasoning": evaluation_reasoning,
        "pass_threshold": pass_threshold,
        "review_threshold": review_threshold,
    }
