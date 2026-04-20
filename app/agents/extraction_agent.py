from __future__ import annotations

import time
from typing import Any

from app.agents.agent_logging import add_agent_audit_log
from app.db.repository import ApplicationRepository
from app.models.state import ApplicationState
from app.tools.extraction import extract_application_from_file


def extraction_agent_node(state: ApplicationState, repo: ApplicationRepository) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        extracted = extract_application_from_file(state["raw_file_path"])
        repo.update_fields(
            state["application_id"],
            name=extracted.get("name"),
            email=extracted.get("email"),
            phone=extracted.get("phone"),
            extracted_json=extracted,
        )
        log = add_agent_audit_log(
            repo,
            state["application_id"],
            "extraction_agent",
            "extract_application_from_file",
            state["raw_file_path"],
            str(extracted),
            start,
        )
        return {"extracted_json": extracted, "audit_log": state["audit_log"] + [log]}
    except Exception as exc:
        repo.append_error(state["application_id"], str(exc))
        raise
