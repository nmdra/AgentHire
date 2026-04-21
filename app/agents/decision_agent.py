"""Mock decision agent for Phase 1 scaffold."""

from __future__ import annotations

from app.observability import traced
from app.state import ApplicationState


@traced("decision_agent")
def decision_agent(_state: ApplicationState) -> dict[str, object]:
    """Return deterministic mocked decision output."""
    return {
        "status": "decided",
        "decision": "REVIEW",
        "confidence": 0.7,
        "decision_reason": "Mocked decision based on static evaluation score.",
    }
