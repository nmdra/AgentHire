"""Local Ollama helper for Decision Agent explanations."""

from __future__ import annotations

import json
import re
from typing import Final

from app.config import get_settings
from app.state import Decision
from app.tools.ollama import OllamaError, extract_first_json, generate_json_response

EXPECTED_KEYS: Final[set[str]] = {"decision_reason", "risk_note"}
MIN_DECISION_REASON_WORDS: Final[int] = 8
DECISION_REFERENCE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(PASS|REVIEW|FAIL)\s+(?:decision|outcome|result)\b", re.IGNORECASE),
    re.compile(r"\b(?:decision|outcome|result)\s+is\s+(PASS|REVIEW|FAIL)\b", re.IGNORECASE),
    re.compile(r"\bshould be\s+(PASS|REVIEW|FAIL)\b", re.IGNORECASE),
    re.compile(r"\bclassified as\s+(PASS|REVIEW|FAIL)\b", re.IGNORECASE),
)


def _word_count(text: str) -> int:
    """Return the number of word-like tokens in a string."""
    return len(re.findall(r"\b\w+\b", text))


def _is_only_decision_label(text: str) -> bool:
    """Return True when text is only PASS, REVIEW, or FAIL."""
    return text.strip().upper() in {"PASS", "REVIEW", "FAIL"}


def _build_prompt(
    *,
    evaluation_score: float,
    pass_threshold: float,
    review_threshold: float,
    decision: Decision,
    confidence: float,
    deterministic_reason: str,
    evaluation_reasoning: str,
) -> str:
    """Create the strict explanation prompt for the local Ollama model."""
    payload = {
        "evaluation_score": round(evaluation_score, 2),
        "pass_threshold": round(pass_threshold, 2),
        "review_threshold": round(review_threshold, 2),
        "decision": decision,
        "confidence": round(confidence, 2),
        "deterministic_reason": deterministic_reason,
        "evaluation_reasoning": evaluation_reasoning,
    }
    return (
        "You are assisting the Decision Agent in a recruitment workflow.\n"
        "A deterministic PASS/REVIEW/FAIL decision has already been computed.\n"
        "Your job is only to explain that existing decision more clearly.\n"
        "Rules:\n"
        "1. Do not change the decision.\n"
        "2. Do not invent candidate details, scores, thresholds, or risks.\n"
        "3. Use only the provided score, thresholds, decision, confidence, "
        "deterministic reason, and evaluation reasoning.\n"
        "4. Return JSON only.\n"
        "5. The decision_reason must stay consistent with the provided decision.\n"
        "6. The decision_reason must be a full sentence, not just PASS, REVIEW, or FAIL.\n"
        "7. The decision_reason must contain at least 8 words.\n"
        "Return exactly this JSON shape:\n"
        '{\n  "decision_reason": "...",\n  "risk_note": "..."\n}\n\n'
        "PROVIDED_DATA:\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )


def _contains_conflicting_decision(text: str, decision: Decision) -> bool:
    """Return True when text explicitly names a different final decision."""
    referenced = {
        match.group(1).upper()
        for pattern in DECISION_REFERENCE_PATTERNS
        for match in pattern.finditer(text)
    }
    return any(label != decision for label in referenced)


def _validate_payload(payload: object, decision: Decision) -> dict[str, str]:
    """Validate and normalize the explanation JSON payload."""
    if not isinstance(payload, dict):
        raise ValueError("Decision explanation payload must be a JSON object")
    if set(payload) != EXPECTED_KEYS:
        raise ValueError("Decision explanation payload keys are invalid")

    decision_reason = str(payload["decision_reason"]).strip()
    risk_note = str(payload["risk_note"]).strip()
    if not decision_reason:
        raise ValueError("decision_reason must not be empty")
    if _is_only_decision_label(decision_reason):
        raise ValueError("decision_reason must not be only the decision label")
    if len(decision_reason) < 24:
        raise ValueError("decision_reason is too short")
    if _word_count(decision_reason) < MIN_DECISION_REASON_WORDS:
        raise ValueError("decision_reason must contain at least 8 words")

    combined = f"{decision_reason} {risk_note}".strip()
    if _contains_conflicting_decision(combined, decision):
        raise ValueError("Decision explanation mentioned a conflicting decision")

    return {
        "decision_reason": decision_reason,
        "risk_note": risk_note,
    }


def generate_decision_explanation(
    *,
    evaluation_score: float,
    pass_threshold: float,
    review_threshold: float,
    decision: Decision,
    confidence: float,
    deterministic_reason: str,
    evaluation_reasoning: str = "",
) -> dict[str, str] | None:
    """Generate a safer human-readable explanation for an existing decision.

    Returns ``None`` when the local Ollama call fails or the response is not safe
    to use, so the Decision Agent can fall back to its deterministic reason.
    """
    settings = get_settings()
    prompt = _build_prompt(
        evaluation_score=evaluation_score,
        pass_threshold=pass_threshold,
        review_threshold=review_threshold,
        decision=decision,
        confidence=confidence,
        deterministic_reason=deterministic_reason,
        evaluation_reasoning=evaluation_reasoning,
    )

    try:
        raw_response = generate_json_response(
            base_url=settings.ollama_base_url,
            model=settings.decision_model,
            prompt=prompt,
            temperature=0.0,
            top_p=0.2,
            num_predict=220,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
        parsed = json.loads(extract_first_json(raw_response))
        return _validate_payload(parsed, decision)
    except (json.JSONDecodeError, OllamaError, TypeError, ValueError):
        return None
