"""Report agent implementation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.observability import traced
from app.state import ApplicationState


def _summarize_candidate(state: ApplicationState) -> str:
    """Build a short candidate summary for reports."""
    extracted = state.get("extracted_json") or {}
    name = extracted.get("name") if isinstance(extracted, dict) else None
    skills = extracted.get("skills") if isinstance(extracted, dict) else None
    skill_count = len(skills) if isinstance(skills, list) else 0
    experience = extracted.get("experience") if isinstance(extracted, dict) else None
    experience_count = len(experience) if isinstance(experience, list) else 0

    parts = [
        f"Candidate: {name or 'Unknown'}",
        f"Skills listed: {skill_count}",
        f"Experience entries: {experience_count}",
    ]
    return "\n".join(parts)

@traced("report_agent")
def report_agent(state: ApplicationState) -> dict[str, object]:
    """Generate applicant-facing and internal reports."""
    settings = get_settings()
    application_id = state.get("application_id", "unknown")

    _write_report(settings.reports_dir, f"{application_id}_applicant.md", applicant_report)
    _write_report(settings.reports_dir, f"{application_id}_internal.md", internal_report)

    return {
        "status": "reported",
        "report_applicant": applicant_report,
        "report_internal": internal_report,
    }
