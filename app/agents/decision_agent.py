"""Decision agent to produce PASS/REVIEW/FAIL from evaluation output."""

from __future__ import annotations

from app.config import get_settings
from app.observability import traced
from app.state import ApplicationState
from app.tools.decision_rules import (
    DEFAULT_PASS_THRESHOLD,
    DEFAULT_REVIEW_THRESHOLD,
    decision_rules_tool,
)
from app.tools.load_rubric import load_rubric_tool


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _extract_thresholds(mapping: dict[str, object]) -> tuple[float, float] | None:
    """Read thresholds from a rubric-like dictionary if present."""
    candidates: list[tuple[str, str]] = [
        ("pass_threshold", "review_threshold"),
        ("pass", "review"),
    ]
    for pass_key, review_key in candidates:
        p = _coerce_float(mapping.get(pass_key))
        r = _coerce_float(mapping.get(review_key))
        if p is not None and r is not None:
            return p, r

    thresholds = mapping.get("decision_thresholds")
    if isinstance(thresholds, dict):
        p = _coerce_float(thresholds.get("pass"))
        r = _coerce_float(thresholds.get("review"))
        if p is not None and r is not None:
            return p, r

    return None


def _load_default_thresholds() -> tuple[float, float]:
    """Load the configured default rubric thresholds, falling back safely if needed."""
    try:
        rubric = dict(
            load_rubric_tool.invoke({"path": get_settings().default_rubric_path})
        )
    except (FileNotFoundError, TypeError, ValueError):
        return DEFAULT_PASS_THRESHOLD, DEFAULT_REVIEW_THRESHOLD

    thresholds = _extract_thresholds(rubric)
    if thresholds is None:
        return DEFAULT_PASS_THRESHOLD, DEFAULT_REVIEW_THRESHOLD
    return thresholds


def _get_thresholds(state: ApplicationState) -> tuple[float, float]:
    """Resolve thresholds from state handoff, rubric state, or safe defaults."""
    direct_thresholds = _extract_thresholds(
        {
            "pass_threshold": state.get("pass_threshold"),
            "review_threshold": state.get("review_threshold"),
        }
    )
    if direct_thresholds is not None:
        return direct_thresholds

    rubric = state.get("rubric")
    if isinstance(rubric, dict):
        rubric_thresholds = _extract_thresholds(rubric)
        if rubric_thresholds is not None:
            return rubric_thresholds

    return _load_default_thresholds()


def _summarize_reasoning(reasoning: object) -> str:
    """Collapse multi-line evaluation reasoning into a short debug-friendly summary."""
    if not reasoning:
        return ""
    summary = " ".join(str(reasoning).split())
    return summary[:277] + "..." if len(summary) > 280 else summary


@traced("decision_agent")
def decision_agent(state: ApplicationState) -> dict[str, object]:
    """Decide PASS/REVIEW/FAIL from evaluation score and resolved thresholds.

    Threshold resolution priority:
    1. ``state.pass_threshold`` / ``state.review_threshold`` — explicit values
       forwarded by the Evaluation Agent.
    2. ``state.rubric`` — a rubric dict stored in state, inspected for
       ``pass_threshold`` / ``review_threshold`` or ``decision_thresholds`` keys.
    3. Default rubric file on disk at ``settings.default_rubric_path`` — loaded
       via :func:`load_rubric_tool` and parsed for threshold keys.
    4. Hard-coded fallbacks: ``DEFAULT_PASS_THRESHOLD`` / ``DEFAULT_REVIEW_THRESHOLD``.
    """
    score = _coerce_float(state.get("evaluation_score"))
    pass_t, review_t = _get_thresholds(state)
    reasoning_summary = _summarize_reasoning(state.get("evaluation_reasoning"))

    if score is None:
        decision_reason = (
            "Decision could not be made from Evaluation Agent output because "
            "evaluation_score is missing; manual review required."
        )
        if reasoning_summary:
            decision_reason = (
                f"{decision_reason} Evaluation reasoning summary: {reasoning_summary}"
            )
        return {
            "status": "decided",
            "decision": "REVIEW",
            "confidence": 0.3,
            "decision_reason": decision_reason,
        }

    decision_result = dict(
        decision_rules_tool.invoke(
            {
                "evaluation_score": score,
                "pass_threshold": pass_t,
                "review_threshold": review_t,
            }
        )
    )
    decision_reason = (
        f"Decision made using Evaluation Agent score {score:.2f}. "
        f"{decision_result['decision_reason']}"
    )
    if reasoning_summary:
        decision_reason = (
            f"{decision_reason} Evaluation reasoning summary: {reasoning_summary}"
        )

    return {
        "status": "decided",
        "decision": str(decision_result["decision"]),
        "confidence": float(decision_result["confidence"]),
        "decision_reason": decision_reason,
    }
