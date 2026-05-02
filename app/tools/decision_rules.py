"""Deterministic decision rules for the Decision Agent."""

from __future__ import annotations

from langchain.tools import tool

from app.state import Decision

DEFAULT_PASS_THRESHOLD = 75.0
DEFAULT_REVIEW_THRESHOLD = 60.0


def _validate_score(score: float) -> float:
    """Validate that the evaluation score is inside the supported range."""
    if not 0.0 <= score <= 100.0:
        raise ValueError("evaluation_score must be between 0 and 100")
    return score


def _validate_thresholds(
    pass_threshold: float,
    review_threshold: float,
) -> tuple[float, float]:
    """Validate threshold ranges and ordering."""
    if not 0.0 <= pass_threshold <= 100.0:
        raise ValueError("pass_threshold must be between 0 and 100")
    if not 0.0 <= review_threshold <= 100.0:
        raise ValueError("review_threshold must be between 0 and 100")
    if pass_threshold < review_threshold:
        raise ValueError(
            "pass_threshold must be greater than or equal to review_threshold"
        )
    return pass_threshold, review_threshold


def _compute_confidence(
    decision: Decision, score: float, pass_threshold: float, review_threshold: float
) -> float:
    """Return a deterministic confidence score between 0 and 1."""
    if decision == "PASS":
        span = max(1.0, 100.0 - pass_threshold)
        confidence = 0.65 + min((score - pass_threshold) / span, 1.0) * 0.34
    elif decision == "FAIL":
        span = max(1.0, review_threshold)
        confidence = 0.65 + min((review_threshold - score) / span, 1.0) * 0.34
    else:
        band = max(1.0, pass_threshold - review_threshold)
        midpoint = (pass_threshold + review_threshold) / 2.0
        max_distance = max(0.5, band / 2.0)
        closeness = max(0.0, 1.0 - (abs(score - midpoint) / max_distance))
        confidence = 0.51 + closeness * 0.18

    return round(max(0.0, min(confidence, 0.99)), 2)


@tool
def decision_rules_tool(
    evaluation_score: float, pass_threshold: float, review_threshold: float
) -> dict[str, object]:
    """Apply deterministic threshold logic to produce a hiring decision.

    Args:
        evaluation_score: Weighted score produced by the Evaluation Agent.
        pass_threshold: Minimum score required for a PASS decision.
        review_threshold: Minimum score required for a REVIEW decision.

    Returns:
        A dictionary containing the decision, confidence, and threshold reason.

    Raises:
        ValueError: If the score or thresholds are invalid.
    """
    score = _validate_score(float(evaluation_score))
    pass_threshold, review_threshold = _validate_thresholds(
        float(pass_threshold),
        float(review_threshold),
    )

    if score >= pass_threshold:
        decision: Decision = "PASS"
        decision_reason = (
            f"Score is greater than or equal to pass threshold {pass_threshold:.2f}."
        )
    elif score >= review_threshold:
        decision = "REVIEW"
        decision_reason = (
            f"Score is below pass threshold {pass_threshold:.2f} but greater than or equal "
            f"to review threshold {review_threshold:.2f}."
        )
    else:
        decision = "FAIL"
        decision_reason = f"Score is below review threshold {review_threshold:.2f}."

    return {
        "decision": decision,
        "confidence": _compute_confidence(
            decision,
            score,
            pass_threshold,
            review_threshold,
        ),
        "decision_reason": decision_reason,
    }
