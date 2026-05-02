from __future__ import annotations

from typing import Any

import pytest

from app.agents.notification_agent import notification_agent


def _base_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "application_id": "app-123",
        "decision": "PASS",
        "extracted_json": {
            "name": "Jane Doe",
            "email": "gayashanhansa1@gmail.com",
        },
        "errors": [],
        "audit_log": [],
    }
    state.update(overrides)
    return state


def test_notification_agent_sends_pass_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "noreply@agenthire.com")

    captured: dict[str, Any] = {}

    def fake_send(payload: dict[str, Any]) -> dict[str, str]:
        captured.update(payload)
        return {"id": "mock-id-123"}

    monkeypatch.setattr("resend.Emails.send", fake_send)

    result = notification_agent(_base_state())

    assert result["notification_status"] == "sent"
    assert captured["to"] == ["gayashanhansa1@gmail.com"]
    assert "passed the current review threshold" in captured["text"]
    assert "moving forward" in captured["subject"]


@pytest.mark.parametrize(
    ("decision", "template_phrase"),
    [
        ("PASS", "passed the current review threshold"),
        ("REVIEW", "under manual review"),
        ("FAIL", "will not be moving forward"),
    ],
)
def test_notification_agent_uses_decision_templates(
    monkeypatch: pytest.MonkeyPatch, decision: str, template_phrase: str
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "noreply@agenthire.com")

    captured: dict[str, Any] = {}

    def fake_send(payload: dict[str, Any]) -> dict[str, str]:
        captured.update(payload)
        return {"id": "mock-id"}

    monkeypatch.setattr("resend.Emails.send", fake_send)

    result = notification_agent(_base_state(decision=decision))

    assert result["notification_status"] == "sent"
    assert template_phrase in captured["text"]


def test_notification_agent_rejects_invalid_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "noreply@agenthire.com")

    send_called = False

    def fake_send(_payload: dict[str, Any]) -> dict[str, str]:
        nonlocal send_called
        send_called = True
        return {"id": "mock-id"}

    monkeypatch.setattr("resend.Emails.send", fake_send)

    result = notification_agent(
        _base_state(extracted_json={"name": "Jane Doe", "email": "invalid-email"})
    )

    assert result["notification_status"] == "failed"
    assert not send_called
    assert any("invalid recipient email address" in error for error in result["errors"])


def test_notification_agent_masks_email_in_audit_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "noreply@agenthire.com")
    monkeypatch.setattr("resend.Emails.send", lambda payload: {"id": "mock-id"})

    result = notification_agent(_base_state())

    audit_entry = result["audit_log"][0]
    assert "gayashanhansa1@gmail.com" not in audit_entry["input_summary"]
    assert "****@gmail.com" in audit_entry["input_summary"]


def test_notification_agent_handles_send_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "noreply@agenthire.com")
    monkeypatch.setattr(
        "resend.Emails.send",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("service unavailable")),
    )

    result = notification_agent(_base_state())

    assert result["notification_status"] == "failed"
    assert any("Email delivery failed" in error for error in result["errors"])
