from __future__ import annotations

from app.agents.decision_agent import _build_decision_prompt
from app.agents.evaluation_agent import _build_evaluation_prompt
from app.agents.extraction_agent import _build_extraction_prompt
from app.agents.notification_agent import _build_notification_prompt
from app.agents.report_agent import _build_report_prompt


def _assert_guardrails(prompt: str) -> None:
    lower = prompt.lower()
    assert "system section" in lower
    assert "task section" in lower
    assert "context section" in lower
    assert "output section" in lower
    assert "no hallucinated fields" in lower
    assert "no secret/api key leakage" in lower
    assert "no overwriting other agents' owned state" in lower


def test_extraction_prompt_contains_persona_and_guardrails() -> None:
    prompt = _build_extraction_prompt("Jane Doe\nPython")
    _assert_guardrails(prompt)
    assert "extraction agent" in prompt.lower()


def test_evaluation_prompt_contains_persona_and_guardrails() -> None:
    prompt = _build_evaluation_prompt({"extracted_json": {"name": "Jane"}})
    _assert_guardrails(prompt)
    assert "evaluation agent" in prompt.lower()


def test_decision_prompt_contains_persona_and_guardrails() -> None:
    prompt = _build_decision_prompt({"evaluation_score": 77.0}, "PASS")
    _assert_guardrails(prompt)
    assert "decision agent" in prompt.lower()


def test_report_prompt_contains_persona_and_guardrails() -> None:
    prompt = _build_report_prompt({"decision": "REVIEW"})
    _assert_guardrails(prompt)
    assert "report agent" in prompt.lower()


def test_notification_prompt_contains_persona_and_guardrails() -> None:
    prompt = _build_notification_prompt({"decision": "PASS"}, "candidate@example.com")
    _assert_guardrails(prompt)
    assert "notification agent" in prompt.lower()
