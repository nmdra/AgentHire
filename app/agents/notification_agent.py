"""Notification agent implementation."""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Template

from app.config import get_settings
from app.observability import traced
from app.state import ApplicationState
from app.tools.send_email import send_email_tool


EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
TEMPLATE_FILENAMES = {
    "PASS": "email_pass.txt",
    "REVIEW": "email_review.txt",
    "FAIL": "email_fail.txt",
}


def _templates_dir() -> Path:
    """Return the root templates directory."""
    return Path(__file__).resolve().parents[2] / "templates"



@traced("notification_agent")
def notification_agent(state: ApplicationState) -> dict[str, object]:
    """Send the decision email and persist the notification outcome."""
    decision = state.get("decision", "REVIEW")
    extracted = state.get("extracted_json") or {}
    recipient = extracted.get("email") if isinstance(extracted, dict) else None

    if not isinstance(recipient, str) or not recipient.strip():
        return {
            "status": "completed",
            "notification_status": "failed",
            "errors": ["notification_agent: missing recipient email address"],
        }

    recipient = recipient.strip()
    if not _is_valid_email(recipient):
        return {
            "status": "completed",
            "notification_status": "failed",
            "errors": [f"notification_agent: invalid recipient email address: {recipient}"],
        }

    body = _render_body(state, decision)
    subject = _build_subject(decision, extracted.get("name") if isinstance(extracted, dict) else None)
    send_result = send_email_tool.invoke(
        {
            "to_address": recipient,
            "subject": subject,
            "body": body,
        }
    )

    if send_result.get("status") != "sent":
        message = str(send_result.get("message", "Email delivery failed"))
        return {
            "status": "completed",
            "notification_status": "failed",
            "errors": [f"notification_agent: {message}"],
        }

    return {
        "status": "completed",
        "notification_status": "sent",
    }
