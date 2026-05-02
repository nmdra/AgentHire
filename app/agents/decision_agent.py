"""Decision agent to produce PASS/REVIEW/FAIL from evaluation output."""

from __future__ import annotations

import re

from app.config import get_settings
from app.observability import traced
from app.state import ApplicationState
from app.tools.decision_explanation import generate_decision_explanation
from app.tools.decision_rules import (
    DEFAULT_PASS_THRESHOLD,
    DEFAULT_REVIEW_THRESHOLD,
    decision_rules_tool,
)
from app.tools.load_rubric import load_rubric_tool


def _word_count(text: str) -> int:
    """Return the number of word-like tokens in a string."""
    return len(re.findall(r"\b\w+\b", text))


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


def _contains_conflicting_decision(text: str, decision: str) -> bool:
    """Return True when a generated explanation names a different outcome."""
    patterns = (
        re.compile(r"\b(PASS|REVIEW|FAIL)\s+(?:decision|outcome|result)\b", re.IGNORECASE),
        re.compile(
            r"\b(?:decision|outcome|result)\s+is\s+(PASS|REVIEW|FAIL)\b",
            re.IGNORECASE,
        ),
        re.compile(r"\bshould be\s+(PASS|REVIEW|FAIL)\b", re.IGNORECASE),
        re.compile(r"\bclassified as\s+(PASS|REVIEW|FAIL)\b", re.IGNORECASE),
    )
    referenced = {
        match.group(1).upper()
        for pattern in patterns
        for match in pattern.finditer(text)
    }
    return any(label != decision for label in referenced)


def _is_low_quality_explanation_text(text: str) -> bool:
    """Return True for explanations that are too weak to show users."""
    normalized = text.strip()
    if not normalized:
        return True
    if normalized.upper() in {"PASS", "REVIEW", "FAIL"}:
        return True
    if len(normalized) < 24:
        return True
    return _word_count(normalized) < 8


def _is_safe_explanation(explanation: dict[str, str] | None, decision: str) -> bool:
    """Validate that an explanation supplement cannot override the final decision."""
    if explanation is None:
        return False

    decision_reason = explanation.get("decision_reason", "")
    if _is_low_quality_explanation_text(decision_reason):
        return False

    combined = " ".join(
        part
        for part in [decision_reason, explanation.get("risk_note", "")]
        if part
    )
    return bool(combined.strip()) and not _contains_conflicting_decision(
        combined, decision
    )


@traced("decision_agent")
def decision_agent(state: ApplicationState) -> dict[str, object]:
    """Decide PASS/REVIEW/FAIL using Evaluation Agent outputs only."""
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
    decision = str(decision_result["decision"])
    confidence = float(decision_result["confidence"])
    decision_reason = (
        f"Decision made using Evaluation Agent score {score:.2f}. "
        f"{decision_result['decision_reason']}"
    )
    if reasoning_summary:
        decision_reason = (
            f"{decision_reason} Evaluation reasoning summary: {reasoning_summary}"
        )

    try:
        explanation = generate_decision_explanation(
            evaluation_score=score,
            pass_threshold=pass_t,
            review_threshold=review_t,
            decision=decision,  # type: ignore[arg-type]
            confidence=confidence,
            deterministic_reason=decision_reason,
            evaluation_reasoning=reasoning_summary,
        )
    except Exception:
        explanation = None
    if _is_safe_explanation(explanation, decision):
        llm_reason = explanation["decision_reason"]
        risk_note = explanation["risk_note"]
        decision_reason = f"{decision_reason} Local Ollama explanation: {llm_reason}"
        if risk_note:
            decision_reason = f"{decision_reason} Risk note: {risk_note}"

    return {
        "status": "decided",
        "decision": decision,
        "confidence": confidence,
        "decision_reason": decision_reason,
    }
