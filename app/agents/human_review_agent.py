from __future__ import annotations

import time
from typing import Any

from app.agents.agent_logging import add_agent_audit_log
from app.db.repository import ApplicationRepository
from app.models.state import ApplicationState


def human_review_node(state: ApplicationState, repo: ApplicationRepository) -> dict[str, Any]:
    start = time.perf_counter()
    status = "queued"
    repo.update_fields(state["application_id"], notification_status=status)
    log = add_agent_audit_log(
        repo,
        state["application_id"],
        "human_review",
        "queue",
        "review decision",
        status,
        start,
    )
    return {"notification_status": status, "audit_log": state["audit_log"] + [log]}
