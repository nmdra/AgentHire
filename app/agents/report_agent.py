"""Report agent implementation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.observability import traced
from app.state import ApplicationState
from app.tools.ollama import OllamaError, generate_json_response
import json
from app.database import update_application


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


def _build_applicant_report(state: ApplicationState) -> str:
    """Create the applicant-facing report body using LLM personalization."""
    decision = state.get("decision", "REVIEW")
    extracted = state.get("extracted_json") or {}
    evaluation_reasoning = state.get("evaluation_reasoning", "")
    settings = get_settings()
    
    # Try LLM personalization first
    if evaluation_reasoning:
        try:
            decision_context = {
                "PASS": "has been accepted and will move forward in our hiring process",
                "REVIEW": "requires additional manual review before a final decision",
                "FAIL": "did not meet our current requirements at this time",
            }.get(decision, "has been reviewed")
            
            prompt = (
                "You are a professional recruiter writing a personalized applicant report.\n"
                "Generate a warm, professional, and concise report summary (2-3 paragraphs).\n"
                "Do NOT include internal scores or technical evaluation details.\n"
                "Focus on: (1) the decision, (2) what they did well, (3) next steps or encouragement.\n"
                "Return JSON only with exactly this key:\n"
                '{"applicant_summary": "string"}\n\n'
                f"Candidate Name: {extracted.get('name', 'Valued Candidate')}\n"
                f"Decision: {decision} - {decision_context}\n"
                f"Evaluation Highlights: {evaluation_reasoning}\n"
                f"Skills: {', '.join(extracted.get('skills', []))}"
            )
            
            response = generate_json_response(
                base_url=settings.ollama_base_url,
                model=settings.extraction_model,
                prompt=prompt,
                temperature=0.3,
                timeout_seconds=settings.ollama_timeout_seconds,
            )
            data = json.loads(response)
            llm_summary = data.get("applicant_summary", "")
            if llm_summary:
                return f"# Applicant Report\n\nDecision: {decision}\n\n{llm_summary}\n\nThank you for submitting your application."
        except (OllamaError, ValueError, json.JSONDecodeError):
            pass  # Fall through to fallback
    
    # Fallback to static template
    decision_message = {
        "PASS": "Your application meets the current review threshold and will move forward.",
        "REVIEW": "Your application requires a manual review before a final hiring step.",
        "FAIL": "Your application did not meet the current review threshold.",
    }.get(decision, "Your application has been reviewed.")

    return "\n".join(
        [
            "# Applicant Report",
            "",
            f"Decision: {decision}",
            "",
            decision_message,
            "",
            _summarize_candidate(state),
            "",
            "Thank you for submitting your application.",
        ]
    )


def _build_internal_report(state: ApplicationState) -> str:
    """Create the internal markdown report body."""
    extracted = state.get("extracted_json") or {}
    skills = extracted.get("skills") if isinstance(extracted, dict) else []
    experience = extracted.get("experience") if isinstance(extracted, dict) else []
    education = extracted.get("education") if isinstance(extracted, dict) else []
    application_id = state.get("application_id", "unknown")
    decision = state.get("decision", "REVIEW")
    confidence = state.get("confidence")
    score = state.get("evaluation_score")
    reasoning = state.get("evaluation_reasoning", "")
    decision_reason = state.get("decision_reason", "")
    created_at = datetime.now(UTC).isoformat()

    return "\n".join(
        [
            "# Internal Report",
            "",
            f"- Application ID: {application_id}",
            f"- Created At: {created_at}",
            f"- Decision: {decision}",
            f"- Confidence: {confidence if confidence is not None else 'n/a'}",
            f"- Evaluation Score: {score if score is not None else 'n/a'}",
            f"- Decision Reason: {decision_reason or 'n/a'}",
            "",
            "## Candidate Snapshot",
            f"- Name: {extracted.get('name') if isinstance(extracted, dict) else 'n/a'}",
            f"- Email: {extracted.get('email') if isinstance(extracted, dict) else 'n/a'}",
            f"- Phone: {extracted.get('phone') if isinstance(extracted, dict) else 'n/a'}",
            f"- Website: {extracted.get('website') if isinstance(extracted, dict) else 'n/a'}",
            f"- Skills: {', '.join(skills) if isinstance(skills, list) and skills else 'None'}",
            f"- Experience Entries: {len(experience) if isinstance(experience, list) else 0}",
            f"- Education Entries: {len(education) if isinstance(education, list) else 0}",
            "",
            "## Evaluation Reasoning",
            reasoning or "n/a",
        ]
    )


def _write_report(directory: str, file_name: str, content: str) -> Path:
    """Write a markdown report to disk and return the path."""
    report_dir = Path(directory)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / file_name
    report_path.write_text(content, encoding="utf-8")
    return report_path


@traced("report_agent")
def report_agent(state: ApplicationState) -> dict[str, object]:
    """Generate applicant-facing and internal reports."""
    settings = get_settings()
    application_id = state.get("application_id")
    applicant_report = _build_applicant_report(state)
    internal_report = _build_internal_report(state)

    _write_report(settings.reports_dir, f"{application_id}_applicant.md", applicant_report)
    _write_report(settings.reports_dir, f"{application_id}_internal.md", internal_report)

    # Persist reports to the database when an application_id is present
    if application_id:
        try:
            update_application(
                settings.db_path,
                application_id,
                {
                    "status": "reported",
                    "report_applicant": applicant_report,
                    "report_internal": internal_report,
                    "errors": state.get("errors", []),
                },
            )
        except Exception:
            # Don't fail the agent if DB persistence fails; log via observability instead
            pass

    return {
        "status": "reported",
        "report_applicant": applicant_report,
        "report_internal": internal_report,
    }