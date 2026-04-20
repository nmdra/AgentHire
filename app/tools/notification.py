from __future__ import annotations

import ssl
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Literal


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
    smtp_host: str = "smtp.mailgun.org",
    smtp_port: int = 587,
    smtp_username: str = "",
    smtp_password: str = "",
    smtp_from: str = "noreply@example.com",
) -> dict[str, str]:
    """Send transactional email via SMTP or queue when credentials absent."""
    email_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    if not smtp_username or not smtp_password:
        return {"email_id": email_id, "status": "queued", "timestamp": now}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_address
    msg.set_content(body)
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=8) as server:
            server.starttls(context=context)
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
        return {"email_id": email_id, "status": "sent", "timestamp": now}
    except Exception:
        return {"email_id": email_id, "status": "failed", "timestamp": now}
