from __future__ import annotations

import time
from typing import Any

from app.core.constants import MAX_SUMMARY_LENGTH
from app.db.repository import ApplicationRepository


def add_agent_audit_log(
    repo: ApplicationRepository,
    application_id: str,
    agent_name: str,
    tool_name: str,
    input_summary: str,
    output_summary: str,
    start_time: float,
) -> dict[str, Any]:
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    repo.add_audit_log(
        application_id=application_id,
        agent_name=agent_name,
        tool_name=tool_name,
        input_summary=input_summary,
        output_summary=output_summary,
        latency_ms=latency_ms,
    )
    return {
        "agent_name": agent_name,
        "tool_name": tool_name,
        "input_summary": input_summary[:MAX_SUMMARY_LENGTH],
        "output_summary": output_summary[:MAX_SUMMARY_LENGTH],
        "latency_ms": latency_ms,
    }
