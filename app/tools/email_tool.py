"""Email notification tool using Resend Python SDK with base64 attachment support."""

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
    to_email: str = Field(description="The recipient email address")
    subject: str = Field(description="The subject of the email")
    body: str = Field(description="The HTML body of the email")
    attachment_path: str | None = Field(None, description="Optional path to a file to attach")
    metadata: dict[str, Any] | None = Field(
        None, description="Optional metadata to include in the email body"
    )

@tool("send_email", args_schema=EmailInput)
def send_email_tool(
    to_email: str,
    subject: str,
    body: str,
    attachment_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Send an email notification via Resend with optional attachments.

    The validation agent decides the subject and body.
    Metadata and attachments can be included for context.
    """
    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("Resend API key not configured. Skipping email.")
        return "Resend API key not configured. Email NOT sent."

    resend.api_key = settings.resend_api_key

    # Enhance body with metadata if provided
    if metadata:
        meta_html = "<h4>Application Metadata:</h4><ul>"
        for k, v in metadata.items():
            meta_html += f"<li>{k}: {v}</li>"
        meta_html += "</ul>"
        body += meta_html

    try:
        params: resend.Emails.SendParams = {
            "from": f"AgentHire <{settings.resend_from_email}>",
            "to": [to_email],
            "subject": subject,
            "html": body,
        }

        # Add attachment if path exists
        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                content = f.read()
                encoded_content = base64.b64encode(content).decode()
                params["attachments"] = [
                    {
                        "filename": os.path.basename(attachment_path),
                        "content": encoded_content,
                    }
                ]
            logger.info(f"Attaching file: {attachment_path} (base64 encoded)")

        logger.info(f"EXTRACTION NOTIFY: Sending email to {to_email}")
        email = resend.Emails.send(params)
        return f"Email sent successfully. ID: {email.get('id')}"
    except Exception as e:
        logger.error(f"EXTRACTION NOTIFY FAILED: {e}")
        return f"Failed to send email: {str(e)}"
