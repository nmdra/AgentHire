"""Shared validation utilities for AgentHire."""

from __future__ import annotations

import re
from pydantic import EmailStr

# Fallback simple regex in case EmailStr validation environment behaves unexpectedly
_SIMPLE_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


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
        # Fall back to a simple regex match for environments where EmailStr may be strict
        return bool(_SIMPLE_EMAIL_RE.fullmatch(addr))
