from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_report_tool(state: dict[str, Any]) -> dict[str, str]:
    """Generate applicant and internal markdown reports from state."""
    applicant = (
        f"# Application Result\n\n"
        f"Decision: **{state.get('decision', 'UNKNOWN')}**\n\n"
        f"Score: {state.get('evaluation_score', 'N/A')}\n"
    )
    internal = (
        "# Internal Evaluation Report\n\n"
        f"Application ID: {state['application_id']}\n\n"
        f"Extracted: {state.get('extracted_json')}\n\n"
        f"Reasoning: {state.get('evaluation_reasoning')}\n"
    )
    return {"report_applicant": applicant, "report_internal": internal}


def save_report_tool(application_id: str, reports_dir: str, applicant: str, internal: str) -> dict[str, str]:
    """Persist generated reports to disk."""
    base = Path(reports_dir)
    base.mkdir(parents=True, exist_ok=True)
    applicant_path = base / f"{application_id}_applicant.md"
    internal_path = base / f"{application_id}_internal.md"
    applicant_path.write_text(applicant, encoding="utf-8")
    internal_path.write_text(internal, encoding="utf-8")
    return {"applicant_path": str(applicant_path), "internal_path": str(internal_path)}
