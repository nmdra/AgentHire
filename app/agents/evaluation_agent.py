"""Evaluation agent implementation."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError

from app.agents.personas import EVALUATION_PERSONA, build_structured_prompt
from app.config import get_settings
from app.observability import traced
from app.state import ApplicationState
from app.tools.ollama import generate_json_response


class EvaluationOutput(BaseModel):
    """Structured output expected from the evaluation model."""

    evaluation_score: float = Field(ge=0.0, le=100.0)
    evaluation_reasoning: str = Field(min_length=1)


def _build_evaluation_prompt(state: ApplicationState) -> str:
    extracted_json = state.get("extracted_json")
    task = (
        "Evaluate candidate quality from extracted data using evidence-based reasoning and assign a score."
    )
    context = json.dumps(
        {"extracted_json": extracted_json},
        ensure_ascii=False,
    )
    output = (
        "Return strict JSON only:\n"
        '{\n'
        '  "evaluation_score": number (0 to 100),\n'
        '  "evaluation_reasoning": string\n'
        '}'
    )
    return build_structured_prompt(
        persona=EVALUATION_PERSONA,
        task=task,
        context=context,
        output=output,
    )


def _run_evaluation_prompt(prompt: str) -> EvaluationOutput:
    settings = get_settings()
    response_text = generate_json_response(
        base_url=settings.ollama_base_url,
        model=settings.evaluation_model,
        prompt=prompt,
        temperature=0.1,
        top_p=0.1,
        stop=["```"],
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    try:
        payload = json.loads(response_text)
        return EvaluationOutput.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Invalid evaluation output: {exc}") from exc


@traced("evaluation_agent")
def evaluation_agent(state: ApplicationState) -> dict[str, object]:
    """Evaluate extracted applicant data and produce score with reasoning."""
    extracted_json = state.get("extracted_json")
    if not isinstance(extracted_json, dict):
        raise ValueError("extracted_json is required for evaluation")

    prompt = _build_evaluation_prompt(state)
    evaluation = _run_evaluation_prompt(prompt)
    return {
        "status": "evaluated",
        "evaluation_score": float(evaluation.evaluation_score),
        "evaluation_reasoning": evaluation.evaluation_reasoning,
    }
