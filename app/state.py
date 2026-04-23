"""Shared LangGraph state for the AgentHire pipeline."""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict
from fastapi import BackgroundTasks


Decision = Literal["PASS", "FAIL", "REVIEW"]


class ApplicationState(TypedDict, total=False):
    """Application state carried between LangGraph nodes."""

    application_id: str
    file_path: str
    background_tasks: BackgroundTasks | None
    status: str
    extracted_json: dict[str, object]
    is_valid: bool
    validation_reason: str
    evaluation_score: float
    evaluation_reasoning: str
    decision: Decision
    confidence: float
    decision_reason: str
    report_applicant: str
    report_internal: str
    notification_status: str
    errors: Annotated[list[str], operator.add]
    audit_log: Annotated[list[dict[str, object]], operator.add]
