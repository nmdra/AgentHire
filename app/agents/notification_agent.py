"""Mock notification agent for Phase 1 scaffold."""

from __future__ import annotations

from app.observability import traced
from app.state import ApplicationState


@traced("notification_agent")
def notification_agent(_state: ApplicationState) -> dict[str, object]:
    """Simulate notification dispatch without external email integration."""
    return {
        "status": "completed",
        "notification_status": "sent",
    }
