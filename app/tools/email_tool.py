"""Email notification tool using Resend Python SDK with base64 attachment support.

This is the single email-sending implementation for AgentHire.  It supports both
HTML emails (for internal reviewer notifications with rich formatting) and
plain-text emails (for candidate-facing decision notifications).
"""

from __future__ import annotations

import base64
import os
from typing import Any

try:
    import resend
except ImportError:  # pragma: no cover - optional dependency fallback
    class _EmailsShim:
        @staticmethod
        def send(_params: dict[str, Any]) -> dict[str, str]:
            raise RuntimeError("resend package is not installed")

    class _ResendShim:
        api_key: str | None = None
        Emails = _EmailsShim

    resend = _ResendShim()

from langchain.tools import tool
from pydantic import BaseModel, Field

from app.config import get_settings
from app.logger import setup_logger

logger = setup_logger("email_tool")


class EmailInput(BaseModel):
    to_address: str = Field(description="The recipient email address")
    subject: str = Field(description="The subject of the email")
    body: str = Field(
        "",
        description="Plain-text message body (used when html_body is not provided)",
    )
    html_body: str | None = Field(
        None,
        description=(
            "Optional HTML body. When provided the email is sent as HTML; "
            "otherwise the plain-text body field is used."
        ),
    )
    attachment_path: str | None = Field(None, description="Optional path to a file to attach")
    metadata: dict[str, Any] | None = Field(
        None, description="Optional metadata to include in the email body"
    )


@tool("send_email", args_schema=EmailInput)
def send_email_tool(
    to_address: str,
    subject: str,
    body: str = "",
    html_body: str | None = None,
    attachment_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send an email via Resend with optional HTML body, attachments, and metadata.

    Pass ``html_body`` for HTML emails (e.g. internal reviewer notifications).
    Omit ``html_body`` to send a plain-text email (e.g. candidate notifications).
    Metadata is appended as HTML when sending HTML, or as plain text otherwise.

    Returns:
        A dict with ``status`` ("sent" or "failed") and an optional ``email_id``.
    """
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("Resend API key not configured. Skipping email.")
        return {"status": "failed", "message": "RESEND_API_KEY is not configured"}
    if not settings.resend_from_email:
        return {"status": "failed", "message": "RESEND_FROM_EMAIL is not configured"}

    resend.api_key = settings.resend_api_key

    params: dict[str, Any] = {
        "from": f"AgentHire <{settings.resend_from_email}>",
        "to": [to_address],
        "subject": subject,
    }

    if html_body is not None:
        # HTML email: append metadata as HTML markup
        if metadata:
            meta_html = "<h4>Application Metadata:</h4><ul>"
            for k, v in metadata.items():
                meta_html += f"<li>{k}: {v}</li>"
            meta_html += "</ul>"
            html_body += meta_html
        params["html"] = html_body

    if body:
        # Plain-text email: append metadata as readable text
        if metadata:
            meta_lines = ["\n\nApplication Metadata:"]
            for k, v in metadata.items():
                meta_lines.append(f"- {k}: {v}")
            body += "\n".join(meta_lines)
        params["text"] = body

    # Add attachment if path exists
    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            encoded_content = base64.b64encode(f.read()).decode()
        params["attachments"] = [
            {
                "filename": os.path.basename(attachment_path),
                "content": encoded_content,
            }
        ]
        logger.info(f"Attaching file: {attachment_path} (base64 encoded)")

    try:
        logger.info(f"Sending email to {to_address}")
        response = resend.Emails.send(params)
    except Exception as exc:
        logger.error(f"Email delivery failed: {exc}")
        return {"status": "failed", "message": "Email delivery failed"}

    result: dict[str, Any] = {"status": "sent", "message": "Email sent"}
    if isinstance(response, dict) and response.get("id") is not None:
        result["email_id"] = str(response["id"])
    return result
