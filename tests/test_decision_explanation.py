"""Unit tests for app/tools/decision_explanation.py."""

from __future__ import annotations

import json

import pytest

from app.tools.decision_explanation import (
    _validate_payload,
    generate_decision_explanation,
)
from app.tools.ollama import OllamaError


# ---------------------------------------------------------------------------
# _validate_payload — acceptance
# ---------------------------------------------------------------------------


def test_validate_payload_accepts_valid_payload() -> None:
    result = _validate_payload(
        {
            "decision_reason": (
                "The candidate demonstrated sufficient skills to pass the evaluation criteria."
            ),
            "risk_note": "Some uncertainty around communication evidence.",
        },
        "PASS",
    )
    assert "demonstrated sufficient skills" in result["decision_reason"]
    assert "uncertainty" in result["risk_note"]


def test_validate_payload_strips_whitespace() -> None:
    result = _validate_payload(
        {
            "decision_reason": (
                "  Score exceeds the pass threshold with strong evidence across all rubric criteria.  "
            ),
            "risk_note": "  note  ",
        },
        "PASS",
    )
    assert not result["decision_reason"].startswith(" ")
    assert not result["decision_reason"].endswith(" ")


# ---------------------------------------------------------------------------
# _validate_payload — rejection: structure
# ---------------------------------------------------------------------------


def test_validate_payload_rejects_non_dict() -> None:
    with pytest.raises(ValueError, match="must be a JSON object"):
        _validate_payload("not a dict", "PASS")


def test_validate_payload_rejects_missing_keys() -> None:
    with pytest.raises(ValueError, match="keys are invalid"):
        _validate_payload({"decision_reason": "Something here for you."}, "PASS")


def test_validate_payload_rejects_extra_keys() -> None:
    with pytest.raises(ValueError, match="keys are invalid"):
        _validate_payload(
            {
                "decision_reason": "Valid reason with enough words in it.",
                "risk_note": "Some note.",
                "unexpected_key": "extra",
            },
            "PASS",
        )


# ---------------------------------------------------------------------------
# _validate_payload — rejection: decision_reason quality
# ---------------------------------------------------------------------------


def test_validate_payload_rejects_empty_decision_reason() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        _validate_payload({"decision_reason": "", "risk_note": "Note"}, "PASS")


def test_validate_payload_rejects_whitespace_only_decision_reason() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        _validate_payload({"decision_reason": "   ", "risk_note": ""}, "PASS")


def test_validate_payload_rejects_label_only_decision_reason() -> None:
    for label in ("PASS", "REVIEW", "FAIL"):
        with pytest.raises(ValueError, match="must not be only the decision label"):
            _validate_payload({"decision_reason": label, "risk_note": ""}, label)  # type: ignore[arg-type]


def test_validate_payload_rejects_too_short_decision_reason() -> None:
    # Under 24 chars but not a bare label
    with pytest.raises(ValueError, match="too short"):
        _validate_payload({"decision_reason": "Short text.", "risk_note": ""}, "PASS")


def test_validate_payload_rejects_too_few_words() -> None:
    # ≥ 24 chars but < 8 words
    with pytest.raises(ValueError, match="at least 8 words"):
        _validate_payload(
            {"decision_reason": "Score is below pass threshold.", "risk_note": ""},
            "REVIEW",
        )


# ---------------------------------------------------------------------------
# _validate_payload — rejection: conflicting decision
# ---------------------------------------------------------------------------


def test_validate_payload_rejects_conflicting_decision_in_reason() -> None:
    with pytest.raises(ValueError, match="conflicting decision"):
        _validate_payload(
            {
                "decision_reason": (
                    "The PASS decision is justified by a strong score across all criteria."
                ),
                "risk_note": "",
            },
            "FAIL",
        )


def test_validate_payload_rejects_conflicting_decision_in_risk_note() -> None:
    with pytest.raises(ValueError, match="conflicting decision"):
        _validate_payload(
            {
                "decision_reason": (
                    "Score is well below the required threshold for further consideration."
                ),
                "risk_note": "The outcome is a PASS decision based on communication skills.",
            },
            "FAIL",
        )


# ---------------------------------------------------------------------------
# generate_decision_explanation — happy path
# ---------------------------------------------------------------------------


def _base_kwargs(**overrides: object) -> dict[str, object]:
    return {
        "evaluation_score": 82.0,
        "pass_threshold": 75.0,
        "review_threshold": 60.0,
        "decision": "PASS",
        "confidence": 0.9,
        "deterministic_reason": "Score 82.00 meets pass threshold 75.00.",
        "evaluation_reasoning": "Strong technical skills demonstrated.",
        **overrides,
    }


def test_generate_decision_explanation_returns_dict_on_valid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid_payload = {
        "decision_reason": (
            "The candidate scored above the pass threshold with strong evidence across all criteria."
        ),
        "risk_note": "Minor uncertainty around soft skills.",
    }
    monkeypatch.setattr(
        "app.tools.decision_explanation.generate_json_response",
        lambda **_kw: json.dumps(valid_payload),
    )
    result = generate_decision_explanation(**_base_kwargs())  # type: ignore[arg-type]
    assert result is not None
    assert "scored above" in result["decision_reason"]
    assert result["risk_note"] == "Minor uncertainty around soft skills."


def test_generate_decision_explanation_accepts_embedded_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model output may include extra text before/after the JSON object."""
    valid_payload = {
        "decision_reason": (
            "The candidate scored above the pass threshold with strong evidence across all criteria."
        ),
        "risk_note": "No significant risk identified in the evaluation.",
    }
    monkeypatch.setattr(
        "app.tools.decision_explanation.generate_json_response",
        lambda **_kw: f"Here is my answer:\n{json.dumps(valid_payload)}\nDone.",
    )
    result = generate_decision_explanation(**_base_kwargs())  # type: ignore[arg-type]
    assert result is not None
    assert "scored above" in result["decision_reason"]


# ---------------------------------------------------------------------------
# generate_decision_explanation — failure cases
# ---------------------------------------------------------------------------


def test_generate_decision_explanation_returns_none_on_ollama_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(**_kw: object) -> str:
        raise OllamaError("connection failed")

    monkeypatch.setattr(
        "app.tools.decision_explanation.generate_json_response",
        _raise,
    )
    result = generate_decision_explanation(**_base_kwargs())  # type: ignore[arg-type]
    assert result is None


def test_generate_decision_explanation_returns_none_on_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.tools.decision_explanation.generate_json_response",
        lambda **_kw: "not json at all",
    )
    result = generate_decision_explanation(**_base_kwargs())  # type: ignore[arg-type]
    assert result is None


def test_generate_decision_explanation_returns_none_when_label_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.tools.decision_explanation.generate_json_response",
        lambda **_kw: json.dumps({"decision_reason": "PASS", "risk_note": ""}),
    )
    result = generate_decision_explanation(**_base_kwargs())  # type: ignore[arg-type]
    assert result is None


def test_generate_decision_explanation_returns_none_when_keys_are_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.tools.decision_explanation.generate_json_response",
        lambda **_kw: json.dumps({"wrong_key": "value", "risk_note": "note"}),
    )
    result = generate_decision_explanation(**_base_kwargs())  # type: ignore[arg-type]
    assert result is None


def test_generate_decision_explanation_returns_none_on_conflicting_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.tools.decision_explanation.generate_json_response",
        lambda **_kw: json.dumps(
            {
                "decision_reason": (
                    "The FAIL decision is based on insufficient score across core criteria."
                ),
                "risk_note": "High risk of poor performance in role.",
            }
        ),
    )
    # decision is PASS but explanation references FAIL
    result = generate_decision_explanation(**_base_kwargs())  # type: ignore[arg-type]
    assert result is None
