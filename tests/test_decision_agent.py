from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.decision_agent import decision_agent
from app.agents.evaluation_agent import evaluation_agent
from app.tools.decision_rules import decision_rules_tool


@pytest.fixture(autouse=True)
def disable_llm_explanation_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Decision Agent unit tests deterministic unless a test overrides this."""
    monkeypatch.setattr(
        "app.agents.decision_agent.generate_decision_explanation",
        lambda **_kwargs: None,
    )


def _base_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "application_id": "app-decision-1",
        "errors": [],
        "audit_log": [],
    }
    state.update(overrides)
    return state


def test_decision_agent_returns_pass_when_score_above_pass_threshold() -> None:
    result = decision_agent(
        _base_state(
            evaluation_score=82.5,
            evaluation_reasoning="Strong rubric alignment across the strongest criteria.",
            pass_threshold=75.0,
            review_threshold=60.0,
        )
    )

    assert result["status"] == "decided"
    assert result["decision"] == "PASS"
    assert 0.0 <= float(result["confidence"]) <= 1.0
    assert "Evaluation Agent score 82.50" in str(result["decision_reason"])


def test_decision_agent_returns_review_when_score_is_between_thresholds() -> None:
    result = decision_agent(
        _base_state(
            evaluation_score=68.55,
            evaluation_reasoning="Candidate is promising but still has some gaps.",
            pass_threshold=70.0,
            review_threshold=50.0,
        )
    )

    assert result["decision"] == "REVIEW"
    assert "below pass threshold 70.00" in str(result["decision_reason"])
    assert "review threshold 50.00" in str(result["decision_reason"])


def test_decision_agent_returns_fail_when_score_is_below_review_threshold() -> None:
    result = decision_agent(
        _base_state(
            evaluation_score=42.0,
            evaluation_reasoning="Several critical rubric gaps remain.",
            pass_threshold=75.0,
            review_threshold=60.0,
        )
    )

    assert result["decision"] == "FAIL"
    assert "below review threshold 60.00" in str(result["decision_reason"])


def test_decision_agent_returns_manual_review_when_score_is_missing() -> None:
    result = decision_agent(
        _base_state(
            evaluation_reasoning="The evaluation model returned a narrative but no final score.",
        )
    )

    assert result["decision"] == "REVIEW"
    assert result["confidence"] == 0.3
    assert "evaluation_score is missing" in str(result["decision_reason"])


def test_decision_agent_includes_evaluation_reasoning_in_reason() -> None:
    reasoning = "Strong technical evidence but moderate communication signal."
    result = decision_agent(
        _base_state(
            evaluation_score=72.0,
            evaluation_reasoning=reasoning,
            pass_threshold=75.0,
            review_threshold=60.0,
        )
    )

    assert reasoning in str(result["decision_reason"])


def test_decision_agent_can_include_llm_generated_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.decision_agent.generate_decision_explanation",
        lambda **_kwargs: {
            "decision_reason": "The score supports a review outcome because it stays below pass level.",
            "risk_note": "There is still some uncertainty around communication evidence.",
        },
    )

    result = decision_agent(
        _base_state(
            evaluation_score=68.55,
            evaluation_reasoning="Candidate is promising but still has some gaps.",
            pass_threshold=70.0,
            review_threshold=50.0,
        )
    )

    assert result["decision"] == "REVIEW"
    assert "Local Ollama explanation:" in str(result["decision_reason"])
    assert "Risk note:" in str(result["decision_reason"])


def test_decision_agent_rejects_llm_explanation_that_conflicts_with_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.decision_agent.generate_decision_explanation",
        lambda **_kwargs: {
            "decision_reason": "This should be a PASS decision because the profile looks excellent.",
            "risk_note": "",
        },
    )

    result = decision_agent(
        _base_state(
            evaluation_score=42.0,
            evaluation_reasoning="Several critical rubric gaps remain.",
            pass_threshold=75.0,
            review_threshold=60.0,
        )
    )

    assert result["decision"] == "FAIL"
    assert "Local Ollama explanation:" not in str(result["decision_reason"])
    assert "Decision made using Evaluation Agent score 42.00." in str(
        result["decision_reason"]
    )


def test_decision_agent_rejects_label_only_llm_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.decision_agent.generate_decision_explanation",
        lambda **_kwargs: {
            "decision_reason": "REVIEW",
            "risk_note": "Assess further details before final hiring decision.",
        },
    )

    result = decision_agent(
        _base_state(
            evaluation_score=68.55,
            evaluation_reasoning="Candidate is promising but still has some gaps.",
            pass_threshold=70.0,
            review_threshold=50.0,
        )
    )

    assert result["decision"] == "REVIEW"
    assert "Local Ollama explanation:" not in str(result["decision_reason"])
    assert "Risk note:" not in str(result["decision_reason"])
    assert str(result["decision_reason"]).startswith(
        "Decision made using Evaluation Agent score 68.55."
    )


def test_decision_agent_falls_back_when_llm_explanation_raises_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_error(**_kwargs: object) -> dict[str, str]:
        raise RuntimeError("Ollama unavailable")

    monkeypatch.setattr(
        "app.agents.decision_agent.generate_decision_explanation",
        _raise_error,
    )

    result = decision_agent(
        _base_state(
            evaluation_score=82.5,
            evaluation_reasoning="Strong rubric alignment across the strongest criteria.",
            pass_threshold=75.0,
            review_threshold=60.0,
        )
    )

    assert result["decision"] == "PASS"
    assert "Local Ollama explanation:" not in str(result["decision_reason"])


def test_decision_agent_uses_rubric_thresholds_from_state() -> None:
    result = decision_agent(
        _base_state(
            evaluation_score=58.0,
            evaluation_reasoning="Candidate is close but not yet strong enough.",
            rubric={"pass_threshold": 80.0, "review_threshold": 55.0},
        )
    )

    assert result["decision"] == "REVIEW"
    assert "pass threshold 80.00" in str(result["decision_reason"])
    assert "review threshold 55.00" in str(result["decision_reason"])


def test_decision_agent_prefers_explicit_threshold_handoff_from_state() -> None:
    result = decision_agent(
        _base_state(
            evaluation_score=68.0,
            evaluation_reasoning="Top-level thresholds should win over rubric fallback.",
            pass_threshold=70.0,
            review_threshold=50.0,
            rubric={"pass_threshold": 65.0, "review_threshold": 45.0},
        )
    )

    assert result["decision"] == "REVIEW"
    assert "pass threshold 70.00" in str(result["decision_reason"])


def test_decision_rules_tool_rejects_invalid_threshold_order() -> None:
    with pytest.raises(
        ValueError,
        match="pass_threshold must be greater than or equal to review_threshold",
    ):
        decision_rules_tool.invoke(
            {
                "evaluation_score": 72.0,
                "pass_threshold": 50.0,
                "review_threshold": 60.0,
            }
        )


@pytest.mark.parametrize("score", [95.0, 68.0, 25.0])
def test_decision_rule_confidence_is_always_between_zero_and_one(score: float) -> None:
    result = decision_rules_tool.invoke(
        {
            "evaluation_score": score,
            "pass_threshold": 75.0,
            "review_threshold": 60.0,
        }
    )

    confidence = float(result["confidence"])
    assert 0.0 <= confidence <= 1.0


def test_evaluation_agent_returns_thresholds_for_decision_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.evaluation_agent.update_application",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.get_settings",
        lambda: SimpleNamespace(db_path="agenthire.db"),
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.evaluate_extracted_json",
        lambda *_args, **_kwargs: {
            "evaluation_score": 68.55,
            "evaluation_reasoning": "Borderline result from evaluation stage.",
            "pass_threshold": 70.0,
            "review_threshold": 50.0,
            "criterion_breakdown": [],
        },
    )

    result = evaluation_agent(
        {
            "application_id": "app-handoff-1",
            "extracted_json": {"name": "Casey Candidate"},
            "errors": [],
            "audit_log": [],
        }
    )

    assert result["evaluation_score"] == 68.55
    assert result["evaluation_reasoning"] == "Borderline result from evaluation stage."
    assert result["pass_threshold"] == 70.0
    assert result["review_threshold"] == 50.0
