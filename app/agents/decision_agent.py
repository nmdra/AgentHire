from __future__ import annotations

import time
from typing import Any

from app.agents.agent_logging import add_agent_audit_log
from app.db.repository import ApplicationRepository
from app.models.state import ApplicationState
from app.tools.decision import apply_decision_rules_tool


def decision_agent_node(state: ApplicationState, repo: ApplicationRepository) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        rubric = state.get("rubric") or {}
        pass_threshold = float(rubric.get("pass_threshold", 75.0))
        review_threshold = float(rubric.get("review_threshold", 60.0))
        decision = apply_decision_rules_tool(
            score=float(state.get("evaluation_score") or 0.0),
            pass_threshold=pass_threshold,
            review_threshold=review_threshold,
        )
        repo.update_fields(
            state["application_id"],
            decision=decision["status"],
            confidence=decision["confidence"],
        )
        log = add_agent_audit_log(
            repo,
            state["application_id"],
            "decision_agent",
            "apply_decision_rules_tool",
            f"score={state.get('evaluation_score')}",
            str(decision),
            start,
        )
        return {
            "decision": decision["status"],
            "confidence": decision["confidence"],
            "audit_log": state["audit_log"] + [log],
        }
    except Exception as exc:
        repo.append_error(state["application_id"], str(exc))
        raise
