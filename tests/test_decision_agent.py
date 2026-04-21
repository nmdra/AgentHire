from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.agents.decision_agent import (
    PASS_THRESHOLD,
    REVIEW_THRESHOLD,
    _classify_score,
    decision_agent,
)


@pytest.fixture
def decision_state() -> dict[str, object]:
    return {
        "application_id": "app-decision-1",
        "evaluation_score": 82.0,
        "evaluation_reasoning": "Strong profile.",
        "errors": [],
        "audit_log": [],
    }


def test_decision_success(monkeypatch: pytest.MonkeyPatch, decision_state: dict[str, object]) -> None:
    monkeypatch.setattr(
        "app.agents.decision_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {"decision_reason": "Score exceeds pass threshold.", "confidence": 0.91}
        ),
    )

    result = decision_agent(decision_state)
    assert result["status"] == "decided"
    assert result["decision"] == "PASS"
    assert float(result["confidence"]) == pytest.approx(0.91)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (75.0, "PASS"),
        (60.0, "REVIEW"),
        (59.99, "FAIL"),
    ],
)
def test_decision_threshold_boundaries(score: float, expected: str) -> None:
    assert _classify_score(score) == expected


@given(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
def test_decision_threshold_property(score: float) -> None:
    decision = _classify_score(score)
    if score >= PASS_THRESHOLD:
        assert decision == "PASS"
    elif score >= REVIEW_THRESHOLD:
        assert decision == "REVIEW"
    else:
        assert decision == "FAIL"


def test_decision_failure_missing_score() -> None:
    result = decision_agent({"application_id": "app-decision-2", "errors": [], "audit_log": []})
    assert result["status"] == "failed"
    assert result["errors"]


def test_decision_uses_fallback_on_invalid_model_output(
    monkeypatch: pytest.MonkeyPatch, decision_state: dict[str, object]
) -> None:
    monkeypatch.setattr("app.agents.decision_agent.generate_json_response", lambda **_kwargs: "invalid-json")
    result = decision_agent(decision_state)
    assert result["status"] == "decided"
    assert result["decision"] == "PASS"
    assert "threshold" in str(result["decision_reason"]).lower()
