from __future__ import annotations

import json

import pytest

from app.agents.notification_agent import _build_notification_prompt, notification_agent


@pytest.fixture
def notification_state() -> dict[str, object]:
    return {
        "application_id": "app-notify-1",
        "decision": "PASS",
        "decision_reason": "Strong score.",
        "report_applicant": "You passed.",
        "extracted_json": {"name": "Jane Doe", "email": "jane@example.com"},
        "errors": [],
        "audit_log": [],
    }


def test_notification_success(
    monkeypatch: pytest.MonkeyPatch, notification_state: dict[str, object]
) -> None:
    class DummySender:
        @staticmethod
        def invoke(*_args: object, **_kwargs: object) -> dict[str, str]:
            return {"status": "sent"}

    monkeypatch.setattr(
        "app.agents.notification_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {"subject": "Application outcome", "body": "You have passed the initial screening."}
        ),
    )
    monkeypatch.setattr("app.agents.notification_agent.send_notification_tool", DummySender())

    result = notification_agent(notification_state)
    assert result["status"] == "completed"
    assert result["notification_status"] == "sent"


def test_notification_edge_invalid_email(notification_state: dict[str, object]) -> None:
    state = {**notification_state, "extracted_json": {"name": "Jane Doe", "email": "bad-email"}}
    result = notification_agent(state)
    assert result["status"] == "completed"
    assert result["notification_status"] == "failed"
    assert result["errors"]


def test_notification_failure_missing_decision() -> None:
    result = notification_agent({"application_id": "app-notify-2", "errors": [], "audit_log": []})
    assert result["status"] == "failed"
    assert result["errors"]


def test_notification_prompt_contract() -> None:
    prompt = _build_notification_prompt({"decision": "REVIEW"}, "candidate@example.com")
    assert '"subject"' in prompt
    assert '"body"' in prompt


def test_notification_masks_email_in_audit_log(
    monkeypatch: pytest.MonkeyPatch, notification_state: dict[str, object]
) -> None:
    class DummySender:
        @staticmethod
        def invoke(*_args: object, **_kwargs: object) -> dict[str, str]:
            return {"status": "sent"}

    monkeypatch.setattr(
        "app.agents.notification_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "subject": "Contact jane@example.com",
                "body": "Reply to jane@example.com for details.",
            }
        ),
    )
    monkeypatch.setattr("app.agents.notification_agent.send_notification_tool", DummySender())

    result = notification_agent(notification_state)
    output_summary = str(result["audit_log"][0].get("output_summary", ""))
    assert "jane@" not in output_summary
