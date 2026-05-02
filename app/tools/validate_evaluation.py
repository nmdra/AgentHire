"""Validation helpers for evaluation-agent reasoning responses."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class EvaluationNarrative(BaseModel):
    """Structured narrative returned by the evaluation model."""

    model_config = ConfigDict(extra="forbid")

    overall_summary: str = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


def _strip_json_fences(text: str) -> str:
    """Strip optional markdown JSON fences from a model response."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if not lines or lines[-1].strip() != "```":
        return stripped
    if lines[0].strip().lower() not in {"```json", "```"}:
        return stripped
    return "\n".join(lines[1:-1]).strip()


def parse_evaluation_narrative(raw_text: str) -> EvaluationNarrative:
    """Parse and validate an evaluation-model JSON response.

    Args:
        raw_text: Raw model response text that should contain a JSON object.

    Returns:
        A validated evaluation narrative model.

    Raises:
        ValueError: If the response is not valid JSON or does not match the schema.

    Example:
        parse_evaluation_narrative('{"overall_summary": "Strong profile.", "strengths": [], "gaps": []}')
    """
    try:
        payload = json.loads(_strip_json_fences(raw_text))
    except json.JSONDecodeError as exc:
        raise ValueError("Evaluation model response was not valid JSON") from exc

    try:
        return EvaluationNarrative.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Evaluation model response failed validation: {exc}") from exc
