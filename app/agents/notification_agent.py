"""Notification agent implementation."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agents.personas import NOTIFICATION_PERSONA, build_structured_prompt
from app.config import get_settings
from app.observability import traced
from app.state import ApplicationState
from app.tools.notification_dispatch import send_notification_tool
from app.tools.ollama import generate_json_response

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class NotificationContent(BaseModel):
    """Structured output expected from notification model."""

    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)


def _build_notification_prompt(state: ApplicationState, recipient: str) -> str:
    task = "Generate a concise plain-text notification email subject and body."
    context = json.dumps(
        {
            "recipient": recipient,
            "name": (state.get("extracted_json") or {}).get("name")
            if isinstance(state.get("extracted_json"), dict)
            else None,
            "decision": state.get("decision"),
            "decision_reason": state.get("decision_reason"),
            "report_applicant": state.get("report_applicant"),
        },
        ensure_ascii=False,
    )
    output = (
        "Return strict JSON only:\n"
        '{\n'
        '  "subject": string,\n'
        '  "body": string\n'
        '}'
    )
    return build_structured_prompt(
        persona=NOTIFICATION_PERSONA,
        task=task,
        context=context,
        output=output,
    )


def _run_notification_prompt(prompt: str) -> NotificationContent:
    settings = get_settings()
    response_text = generate_json_response(
        base_url=settings.ollama_base_url,
        model=settings.notification_model,
        prompt=prompt,
        temperature=0.2,
        top_p=0.1,
        stop=["```"],
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    try:
        payload = json.loads(response_text)
        return NotificationContent.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Invalid notification output: {exc}") from exc


def _extract_recipient(state: ApplicationState) -> str | None:
    extracted = state.get("extracted_json")
    if not isinstance(extracted, dict):
        return None
    email = extracted.get("email")
    if isinstance(email, str) and email:
        return email
    return None


@traced("notification_agent")
def notification_agent(state: ApplicationState) -> dict[str, Any]:
    """Generate and dispatch a notification payload."""
    if state.get("decision") is None:
        raise ValueError("decision is required for notification")

    recipient = _extract_recipient(state)
    if recipient is None or not EMAIL_PATTERN.fullmatch(recipient):
        return {
            "status": "completed",
            "notification_status": "failed",
            "errors": ["notification_agent failed: missing or invalid recipient email"],
        }

    prompt = _build_notification_prompt(state, recipient)
    content = _run_notification_prompt(prompt)
    dispatch_result = send_notification_tool.invoke(
        {
            "to_address": recipient,
            "subject": content.subject,
            "body": content.body,
        }
    )
    return {
        "status": "completed",
        "notification_status": dispatch_result.get("status", "failed"),
    }
