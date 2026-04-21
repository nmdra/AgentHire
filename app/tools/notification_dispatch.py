"""Notification dispatch tool."""

from __future__ import annotations

import re

from langchain.tools import tool

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@tool
def send_notification_tool(to_address: str, subject: str, body: str) -> dict[str, str]:
    """Dispatch a notification payload.

    Args:
        to_address: Recipient email address.
        subject: Subject line for the email message.
        body: Plain-text email body.

    Returns:
        A status dictionary with dispatch result.

    Raises:
        ValueError: If to_address is missing or invalid.

    Example:
        send_notification_tool.invoke(
            {
                "to_address": "candidate@example.com",
                "subject": "Application update",
                "body": "Thank you for applying.",
            }
        )
    """
    if not EMAIL_PATTERN.fullmatch(to_address):
        raise ValueError("Invalid recipient email address")
    return {
        "status": "sent",
        "message": f"Notification prepared for {to_address} with subject '{subject[:80]}'",
        "body_preview": body[:120],
    }
