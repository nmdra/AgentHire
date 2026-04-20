from typing import Any, Literal, NotRequired, TypedDict


class AuditLogEntry(TypedDict):
    agent_name: str
    tool_name: str
    input_summary: str
    output_summary: str
    latency_ms: int


class ApplicationState(TypedDict):
    application_id: str
    raw_file_path: str
    extracted_json: NotRequired[dict[str, Any] | None]
    rubric: NotRequired[dict[str, Any] | None]
    evaluation_score: NotRequired[float | None]
    evaluation_reasoning: NotRequired[str | None]
    decision: NotRequired[Literal["PASS", "FAIL", "REVIEW"] | None]
    confidence: NotRequired[float | None]
    report_applicant: NotRequired[str | None]
    report_internal: NotRequired[str | None]
    notification_status: NotRequired[str | None]
    errors: list[str]
    audit_log: list[AuditLogEntry]
