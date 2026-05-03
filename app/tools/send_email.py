"""Email sending tool for AgentHire."""

from __future__ import annotations

from typing import Any

import base64
import os

import resend
from langchain.tools import tool

from app.config import get_settings


@tool
def send_email_tool(
    to_address: str,
    subject: str,
    body: str,
    attachment_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a plain-text email through Resend.

    Args:
        to_address: Recipient email address.
        subject: Email subject line.
        body: Plain-text message body.

    Returns:
        A dictionary describing whether the send succeeded.

    Raises:
        ValueError: If required arguments are empty.

    Example:
        send_email_tool.invoke({
            "to_address": "candidate@example.com",
            "subject": "Application update",
            "body": "Hello, ...",
        })
    """
    if not to_address or not to_address.strip():
        raise ValueError("Recipient email address is required")
    if not subject.strip():
        raise ValueError("Email subject is required")
    if not body.strip():
        raise ValueError("Email body is required")

    # Delegate to the richer email tool implementation (handles attachments/html/metadata)
    settings = get_settings()
    if not settings.resend_api_key:
        return {"status": "failed", "message": "RESEND_API_KEY is not configured"}
    if not settings.resend_from_email:
        return {"status": "failed", "message": "RESEND_FROM_EMAIL is not configured"}

    try:
        resend.api_key = settings.resend_api_key

        if metadata:
            meta_lines = ["<h4>Application Metadata:</h4><ul>"]
            for key, value in metadata.items():
                meta_lines.append(f"<li>{key}: {value}</li>")
            meta_lines.append("</ul>")
            body = body + "".join(meta_lines)

        params: dict[str, Any] = {
            "from": settings.resend_from_email,
            "to": [to_address],
            "subject": subject,
            "text": body,
        }

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as file_handle:
                params["attachments"] = [
                    {
                        "filename": os.path.basename(attachment_path),
                        "content": base64.b64encode(file_handle.read()).decode(),
                    }
                ]

        response = resend.Emails.send(params)
    except Exception as exc:  # pragma: no cover - defensive integration guard
        return {"status": "failed", "message": f"Email delivery failed: {exc}"}

    result: dict[str, Any] = {"status": "sent", "message": "Email sent"}
    if isinstance(response, dict) and response.get("id") is not None:
        result["email_id"] = str(response["id"])
    return result