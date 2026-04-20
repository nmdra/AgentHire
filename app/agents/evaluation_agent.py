from __future__ import annotations

import time
from typing import Any

from app.agents.agent_logging import add_agent_audit_log
from app.db.repository import ApplicationRepository
from app.models.state import ApplicationState
from app.tools.evaluation import load_rubric_tool, score_against_rubric_tool


def evaluation_agent_node(state: ApplicationState, repo: ApplicationRepository) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        rubric = load_rubric_tool(state.get("rubric"))
        scored = score_against_rubric_tool(state.get("extracted_json") or {}, rubric)
        repo.update_fields(
            state["application_id"],
            evaluation_score=scored["total_score"],
            evaluation_reasoning=scored["reasoning"],
        )
        log = add_agent_audit_log(
            repo,
            state["application_id"],
            "evaluation_agent",
            "score_against_rubric_tool",
            str(rubric),
            str(scored),
            start,
        )
        return {
            "rubric": rubric,
            "evaluation_score": scored["total_score"],
            "evaluation_reasoning": scored["reasoning"],
            "audit_log": state["audit_log"] + [log],
        }
    except Exception as exc:
        repo.append_error(state["application_id"], str(exc))
        raise
