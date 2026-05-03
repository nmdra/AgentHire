"""Notification agent implementation."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from app.observability import traced
from app.state import ApplicationState
from app.config import get_settings
from app.tools.ollama import OllamaError, generate_json_response
import json
from app.tools.email_tool import send_email_tool


from app.utils.validation import is_valid_email
TEMPLATE_FILENAMES = {
    "PASS": "email_pass.txt",
    "REVIEW": "email_review.txt",
    "FAIL": "email_fail.txt",
}


def _templates_dir() -> Path:
    """Return the root templates directory."""
    return Path(__file__).resolve().parents[2] / "templates"

# Use shared Pydantic-based validator from app.utils.validation

def _load_template(decision: str) -> str:
    """Load the body template for a decision branch."""
    template_name = TEMPLATE_FILENAMES.get(decision, TEMPLATE_FILENAMES["REVIEW"])
    template_path = _templates_dir() / template_name
    if not template_path.exists():
        raise FileNotFoundError(f"Missing notification template: {template_path}")
    return template_path.read_text(encoding="utf-8")

def _build_subject(decision: str, candidate_name: str | None) -> str:
    """Build a short, readable subject line."""
    base = {
        "PASS": "Your AgentHire application is moving forward",
        "REVIEW": "Your AgentHire application is under review",
        "FAIL": "Update on your AgentHire application",
    }.get(decision, "Your AgentHire application update")
    if candidate_name:
        return f"{base} - {candidate_name}"
    return base

def _render_body(state: ApplicationState, decision: str) -> str:
    """Render a decision-specific body using LLM personalization with template fallback."""
    extracted = state.get("extracted_json") or {}
    candidate_name = extracted.get("name") if isinstance(extracted, dict) else None
    evaluation_reasoning = state.get("evaluation_reasoning", "")
    # Only include candidate-safe signals: name, decision context, and publicly known skills.
    # evaluation_reasoning is intentionally excluded from the prompt to prevent internal
    # scoring details from leaking into candidate-facing emails.
    skills: list[str] = extracted.get("skills", []) if isinstance(extracted, dict) else []  # type: ignore[assignment]

    # Try LLM personalization when we have evaluation context (gate on reasoning being set)
    if evaluation_reasoning:
        try:
            settings = get_settings()
            decision_context = {
                "PASS": "has been accepted and will move forward in our hiring process",
                "REVIEW": "requires additional manual review before a final decision",
                "FAIL": "did not meet our current requirements at this time",
            }.get(decision, "has been reviewed")

            prompt = (
                "You are a professional recruiter sending a personalized decision email to a job candidate.\n"
                "Write a warm, encouraging, and professional email body (2-3 paragraphs).\n"
                "Do NOT include internal scores or technical evaluation details.\n"
                "Focus on: (1) the decision, (2) next steps or encouragement.\n"
                "Return JSON only with exactly this key:\n"
                '{"email_body": "string"}\n\n'
                f"Candidate: {candidate_name or 'Valued Candidate'}\n"
                f"Decision: {decision} - {decision_context}\n"
                f"Skills: {', '.join(skills)}"
            )

            response = generate_json_response(
                base_url=settings.ollama_base_url,
                model=settings.notification_model,
                prompt=prompt,
                temperature=0.4,
                timeout_seconds=settings.ollama_timeout_seconds,
            )
            data = json.loads(response)
            llm_body = data.get("email_body", "")
            if llm_body:
                return llm_body
        except (OllamaError, ValueError, json.JSONDecodeError):
            pass  # Fall through to template-based fallback

    # Fallback to Jinja2 template
    template_text = _load_template(decision)
    return Template(template_text).render(
        name=candidate_name or "there",
        application_id=state.get("application_id", "unknown"),
        decision=decision,
    )

@traced("notification_agent")
def notification_agent(state: ApplicationState) -> dict[str, object]:
    """Send the decision email and return  the notification outcome."""
    decision = state.get("decision", "REVIEW")
    extracted = state.get("extracted_json") or {}
    recipient = extracted.get("email") if isinstance(extracted, dict) else None

    if not isinstance(recipient, str) or not recipient.strip():
        return {
            "status": "completed",
            "notification_status": "failed",
            "errors": ["notification_agent: missing recipient email address"],
        }

    recipient = recipient.strip()
    if not is_valid_email(recipient):
        return {
            "status": "completed",
            "notification_status": "failed",
            "errors": ["notification_agent: invalid recipient email address"],
        }

    body = _render_body(state, decision)
    subject = _build_subject(decision, extracted.get("name") if isinstance(extracted, dict) else None)
    send_result = send_email_tool.invoke(
        {
            "to_address": recipient,
            "subject": subject,
            "body": body,
        }
    )

    if send_result.get("status") != "sent":
        message = str(send_result.get("message", "Email delivery failed"))
        return {
            "status": "completed",
            "notification_status": "failed",
            "errors": [f"notification_agent: {message}"],
        }

    return {
        "status": "completed",
        "notification_status": "sent",
    }
