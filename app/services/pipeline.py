from __future__ import annotations

from typing import Any

from app.db.repository import ApplicationRepository
from app.graph.workflow import build_workflow
from app.models.state import ApplicationState


def process_application(
    repo: ApplicationRepository,
    application_id: str,
    raw_file_path: str,
    rubric: dict[str, Any] | None,
    reports_dir: str,
    email_config: dict[str, Any],
    retries: int,
) -> None:
    flow = build_workflow(repo=repo, reports_dir=reports_dir, email_config=email_config, retries=retries)
    initial_state: ApplicationState = {
        "application_id": application_id,
        "raw_file_path": raw_file_path,
        "extracted_json": None,
        "rubric": rubric,
        "evaluation_score": None,
        "evaluation_reasoning": None,
        "decision": None,
        "confidence": None,
        "report_applicant": None,
        "report_internal": None,
        "notification_status": None,
        "errors": [],
        "audit_log": [],
    }
    try:
        flow.invoke(initial_state)
    except Exception as exc:  # pragma: no cover
        repo.append_error(application_id, f"Pipeline failed: {exc}")
