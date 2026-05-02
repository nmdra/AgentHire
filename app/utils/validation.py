"""Shared validation utilities for AgentHire."""

from __future__ import annotations

from pydantic import EmailStr


def is_valid_email(address: str) -> bool:
    """Validate an email address using Pydantic's EmailStr.

    Returns True for syntactically valid email addresses, False otherwise.
    """
    if not isinstance(address, str):
        return False
    addr = address.strip()
    if not addr:
        return False
    try:
        # EmailStr will raise if invalid
        EmailStr(addr)
        return True
    except Exception:
        return False
