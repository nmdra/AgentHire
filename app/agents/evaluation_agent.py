"""Mock evaluation agent for Phase 1 scaffold."""

from __future__ import annotations

from app.observability import traced
from app.state import ApplicationState


@traced("evaluation_agent")
def evaluation_agent(_state: ApplicationState) -> dict[str, object]:
    """Return deterministic mocked evaluation output."""
    return {
        "status": "evaluated",
        "evaluation_score": 72.0,
        "evaluation_reasoning": "Mocked rubric evaluation for scaffold run.",
    }
