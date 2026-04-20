from __future__ import annotations

from app.models.schemas import DecisionResult


def apply_decision_rules_tool(
    score: float,
    pass_threshold: float = 75.0,
    review_threshold: float = 60.0,
) -> dict[str, str | float]:
    """Apply threshold-based business logic to produce classification."""
    if score >= pass_threshold:
        result = DecisionResult(
            status="PASS",
            confidence=min(score / 100.0, 1.0),
            reason="Score meets pass threshold",
        )
    elif score >= review_threshold:
        result = DecisionResult(
            status="REVIEW",
            confidence=0.5,
            reason="Score requires human review",
        )
    else:
        result = DecisionResult(
            status="FAIL",
            confidence=max(0.0, 1.0 - score / 100.0),
            reason="Score below minimum threshold",
        )
    return result.model_dump()
