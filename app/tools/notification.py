from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

import resend


def compose_email_tool(
    decision: Literal["PASS", "FAIL", "REVIEW"], recipient_name: str | None
) -> dict[str, str]:
    """Compose outcome-specific email content."""
    salutation = recipient_name or "Applicant"
    if decision == "PASS":
        subject = "Application Update: Accepted"
        body = f"Dear {salutation},\n\nCongratulations! Your application has been accepted."
    elif decision == "REVIEW":
        subject = "Application Update: Under Review"
        body = f"Dear {salutation},\n\nYour application requires additional human review."
    else:
        subject = "Application Update: Decision"
        body = f"Dear {salutation},\n\nThank you for applying. At this time, we cannot proceed."
    return {"subject": subject, "body": body}


def send_email_tool(
    to_address: str,
    subject: str,
    body: str,
    resend_api_key: str = "",
    resend_from_email: str = "noreply@example.com",
) -> dict[str, str]:
    """Send transactional email via Resend or queue when not configured."""
    email_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    if not resend_api_key:
        return {"email_id": email_id, "status": "queued", "timestamp": now}
    if not to_address:
        return {"email_id": email_id, "status": "failed", "timestamp": now}

    try:
        resend.api_key = resend_api_key
        result = resend.Emails.send(
            {
                "from": resend_from_email,
                "to": [to_address],
                "subject": subject,
                "text": body,
            }
        )
        resolved_id = str(result.get("id", email_id)) if isinstance(result, dict) else email_id
        return {"email_id": resolved_id, "status": "sent", "timestamp": now}
    except Exception:
        return {"email_id": email_id, "status": "failed", "timestamp": now}
