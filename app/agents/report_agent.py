from __future__ import annotations

import time
from typing import Any

from app.tools.agent_logging import add_agent_audit_log
from app.tools.repository import ApplicationRepository
from app.models.state import ApplicationState
from app.tools.reporting import generate_report_tool, save_report_tool


def report_agent_node(state: ApplicationState, repo: ApplicationRepository, reports_dir: str) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        reports = generate_report_tool(dict(state))
        save_report_tool(
            state["application_id"],
            reports_dir,
            reports["report_applicant"],
            reports["report_internal"],
        )
        repo.update_fields(
            state["application_id"],
            report_applicant=reports["report_applicant"],
            report_internal=reports["report_internal"],
        )
        log = add_agent_audit_log(
            repo,
            state["application_id"],
            "report_agent",
            "generate_report_tool",
            str(state.get("decision") or "unknown"),
            "reports_generated",
            start,
        )
        return {
            "report_applicant": reports["report_applicant"],
            "report_internal": reports["report_internal"],
            "audit_log": state["audit_log"] + [log],
        }
    except Exception as exc:
        repo.append_error(state["application_id"], str(exc))
        raise
