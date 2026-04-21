"""Report agent implementation."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError

from app.agents.personas import REPORT_PERSONA, build_structured_prompt
from app.config import get_settings
from app.observability import traced
from app.state import ApplicationState
from app.tools.ollama import generate_json_response
from app.tools.report_writer import write_reports_tool


class ReportOutput(BaseModel):
    """Structured report output expected from the report model."""

    report_applicant: str = Field(min_length=1)
    report_internal: str = Field(min_length=1)


def _build_report_prompt(state: ApplicationState) -> str:
    task = (
        "Generate two markdown reports: an applicant-facing summary and an internal structured report."
    )
    context = json.dumps(
        {
            "name": (state.get("extracted_json") or {}).get("name")
            if isinstance(state.get("extracted_json"), dict)
            else None,
            "decision": state.get("decision"),
            "decision_reason": state.get("decision_reason"),
            "evaluation_score": state.get("evaluation_score"),
            "evaluation_reasoning": state.get("evaluation_reasoning"),
            "skills": (state.get("extracted_json") or {}).get("skills")
            if isinstance(state.get("extracted_json"), dict)
            else None,
            "other_details": (state.get("extracted_json") or {}).get("other_details")
            if isinstance(state.get("extracted_json"), dict)
            else None,
        },
        ensure_ascii=False,
    )
    output = (
        "Return strict JSON only:\n"
        '{\n'
        '  "report_applicant": string markdown,\n'
        '  "report_internal": string markdown\n'
        '}'
    )
    return build_structured_prompt(
        persona=REPORT_PERSONA,
        task=task,
        context=context,
        output=output,
    )


def _run_report_prompt(prompt: str) -> ReportOutput:
    settings = get_settings()
    response_text = generate_json_response(
        base_url=settings.ollama_base_url,
        model=settings.report_model,
        prompt=prompt,
        temperature=0.3,
        top_p=0.2,
        stop=["```"],
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    try:
        payload = json.loads(response_text)
        return ReportOutput.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"Invalid report output: {exc}") from exc


@traced("report_agent")
def report_agent(state: ApplicationState) -> dict[str, object]:
    """Generate applicant and internal reports from pipeline state."""
    if state.get("decision") is None:
        raise ValueError("decision is required for reporting")

    settings = get_settings()
    prompt = _build_report_prompt(state)
    reports = _run_report_prompt(prompt)

    application_id = state.get("application_id")
    if isinstance(application_id, str) and application_id:
        write_reports_tool.invoke(
            {
                "reports_dir": settings.reports_dir,
                "application_id": application_id,
                "report_applicant": reports.report_applicant,
                "report_internal": reports.report_internal,
            }
        )

    return {
        "status": "reported",
        "report_applicant": reports.report_applicant,
        "report_internal": reports.report_internal,
    }
