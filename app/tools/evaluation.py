from __future__ import annotations

from typing import Any

from app.models.schemas import Rubric, ScoreBreakdown


def load_rubric_tool(rubric_data: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and normalize rubric payload."""
    if rubric_data is None:
        rubric_data = {
            "criteria": [
                {"name": "Technical Skills", "weight": 0.40, "description": "Relevant technical depth"},
                {"name": "Experience", "weight": 0.30, "description": "Relevant experience evidence"},
                {"name": "Communication", "weight": 0.20, "description": "Clarity and structure"},
                {"name": "Education", "weight": 0.10, "description": "Education relevance"},
            ],
            "pass_threshold": 65,
            "review_threshold": 60,
        }
    return Rubric.model_validate(rubric_data).model_dump()


def _criterion_raw_score(extracted_json: dict[str, Any], criterion_name: str) -> float:
    name = criterion_name.lower()
    if "skill" in name:
        return min(100.0, 25.0 * len(extracted_json.get("skills", [])))
    if "experience" in name:
        return min(100.0, 33.3 * len(extracted_json.get("experience", [])))
    if "education" in name:
        return min(100.0, 50.0 * len(extracted_json.get("education", [])))
    completeness = sum(
        1 for k in ["name", "email", "phone", "website"] if extracted_json.get(k)
    ) / 4.0
    return round(completeness * 100.0, 2)


def score_against_rubric_tool(extracted_json: dict[str, Any], rubric: dict[str, Any]) -> dict[str, Any]:
    """Score extracted application against weighted rubric."""
    validated = Rubric.model_validate(rubric)
    breakdown: dict[str, float] = {}
    weighted_total = 0.0
    reasons: list[str] = []
    for criterion in validated.criteria:
        raw = _criterion_raw_score(extracted_json, criterion.name)
        weighted_total += raw * criterion.weight
        breakdown[criterion.name] = round(raw, 2)
        reasons.append(f"{criterion.name}: {raw:.2f}/100 (weight {criterion.weight:.2f})")

    result = ScoreBreakdown(
        total_score=round(weighted_total, 2),
        breakdown=breakdown,
        reasoning="; ".join(reasons),
    )
    return result.model_dump()
