from __future__ import annotations

import time
from typing import Any, Literal

from app.tools.agent_logging import add_agent_audit_log
from app.tools.repository import ApplicationRepository
from app.models.state import ApplicationState
from app.tools.notification import compose_email_tool, send_email_tool


def notification_agent_node(
    state: ApplicationState, repo: ApplicationRepository, email_config: dict[str, Any]
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        extracted = state.get("extracted_json") or {}
        recipient = str(extracted.get("email") or "")
        decision_state = state.get("decision")
        decision: Literal["PASS", "FAIL", "REVIEW"]
        if decision_state == "PASS":
            decision = "PASS"
        elif decision_state == "REVIEW":
            decision = "REVIEW"
        else:
            decision = "FAIL"
        if not recipient:
            status = "failed"
            error = "Missing recipient email"
            repo.append_error(state["application_id"], error)
            repo.update_fields(state["application_id"], notification_status=status)
            log = add_agent_audit_log(
                repo,
                state["application_id"],
                "notification_agent",
                "validate_recipient",
                "missing email",
                status,
                start,
            )
            return {
                "notification_status": status,
                "errors": state["errors"] + [error],
                "audit_log": state["audit_log"] + [log],
            }
        recipient_name = extracted.get("name")
        composed = compose_email_tool(decision, str(recipient_name) if recipient_name else None)
        sent = send_email_tool(
            to_address=recipient,
            subject=composed["subject"],
            body=composed["body"],
            resend_api_key=str(email_config.get("resend_api_key", "")),
            resend_from_email=str(email_config.get("resend_from_email", "noreply@example.com")),
        )
        repo.update_fields(state["application_id"], notification_status=sent["status"])
        log = add_agent_audit_log(
            repo,
            state["application_id"],
            "notification_agent",
            "send_email_tool",
            recipient,
            str(sent),
            start,
        )
        return {"notification_status": sent["status"], "audit_log": state["audit_log"] + [log]}
    except Exception as exc:
        repo.append_error(state["application_id"], str(exc))
        raise
