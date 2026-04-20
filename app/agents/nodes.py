from __future__ import annotations

import time
from typing import Any

from app.db.repository import ApplicationRepository
from app.models.state import ApplicationState
from app.tools.decision import apply_decision_rules_tool
from app.tools.evaluation import load_rubric_tool, score_against_rubric_tool
from app.tools.extraction import extract_application_from_file
from app.tools.notification import compose_email_tool, send_email_tool
from app.tools.reporting import generate_report_tool, save_report_tool


def _log(
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
        "input_summary": input_summary[:500],
        "output_summary": output_summary[:500],
        "latency_ms": latency_ms,
    }


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
        log = _log(
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
        return {"errors": state["errors"] + [str(exc)]}


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
        log = _log(
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
        return {"errors": state["errors"] + [str(exc)]}


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
        log = _log(
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
        return {"errors": state["errors"] + [str(exc)]}


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
        log = _log(
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
        return {"errors": state["errors"] + [str(exc)]}


def notification_agent_node(state: ApplicationState, repo: ApplicationRepository, smtp_config: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        extracted = state.get("extracted_json") or {}
        recipient = str(extracted.get("email") or "")
        decision = str(state.get("decision") or "FAIL")
        composed = compose_email_tool(decision, str(extracted.get("name") or "Applicant"))
        sent = send_email_tool(
            to_address=recipient,
            subject=composed["subject"],
            body=composed["body"],
            smtp_host=str(smtp_config.get("smtp_host", "smtp.mailgun.org")),
            smtp_port=int(smtp_config.get("smtp_port", 587)),
            smtp_username=str(smtp_config.get("smtp_username", "")),
            smtp_password=str(smtp_config.get("smtp_password", "")),
            smtp_from=str(smtp_config.get("smtp_from", "noreply@example.com")),
        )
        repo.update_fields(state["application_id"], notification_status=sent["status"])
        log = _log(
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
        return {"errors": state["errors"] + [str(exc)]}


def human_review_node(state: ApplicationState, repo: ApplicationRepository) -> dict[str, Any]:
    start = time.perf_counter()
    status = "queued"
    repo.update_fields(state["application_id"], notification_status=status)
    log = _log(
        repo,
        state["application_id"],
        "human_review",
        "queue",
        "review decision",
        status,
        start,
    )
    return {"notification_status": status, "audit_log": state["audit_log"] + [log]}
