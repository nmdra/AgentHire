"""Notification agent implementation."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from jinja2 import Template

from app.config import get_settings
from app.observability import traced
from app.state import ApplicationState
from app.tools.email_tool import send_email_tool
from app.tools.ollama import OllamaError, generate_json_response
from app.utils.validation import is_valid_email

TEMPLATE_FILENAMES = {
    "PASS": "email_pass.txt",
    "REVIEW": "email_review.txt",
    "FAIL": "email_fail.txt",
}


def _templates_dir() -> Path:
    """Return the root templates directory."""
    return Path(__file__).resolve().parents[2] / "templates"


def _load_template(filename: str) -> str:
    """Load a specific template file."""
    template_path = _templates_dir() / filename
    if not template_path.exists():
        raise FileNotFoundError(f"Missing template: {template_path}")
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


def _wrap_in_html(body_text: str, settings: object) -> str:
    """Wrap plain text body into the base HTML template."""
    # Convert double newlines to paragraphs, single newlines to breaks
    formatted_body = "".join(f"<p>{p.strip()}</p>" for p in body_text.split("\n\n") if p.strip())
    formatted_body = formatted_body.replace("\n", "<br>")

    base_html = _load_template("base_email.html")
    return Template(base_html).render(
        company_name=getattr(settings, "company_name", "AgentHire"),
        body_html=formatted_body,
        current_year=datetime.now().year,
    )


def _render_notification(state: ApplicationState, decision: str) -> tuple[str, str, str]:
    """Render a decision-specific subject, plain body, and HTML body."""
    extracted = state.get("extracted_json") or {}
    candidate_name = extracted.get("name") if isinstance(extracted, dict) else None
    evaluation_reasoning = state.get("evaluation_reasoning", "")
    skills: list[str] = (
        extracted.get("skills", []) if isinstance(extracted, dict) else []
    )  # type: ignore[assignment]
    experience: list[dict[str, str]] = (
        extracted.get("experience", []) if isinstance(extracted, dict) else []
    )  # type: ignore[assignment]
    settings = get_settings()

    final_subject = ""
    final_body = ""

    # Try LLM personalization when we have evaluation context
    if evaluation_reasoning:
        try:
            settings = get_settings()

            # Map raw decision to natural language for the LLM
            friendly_status = {
                "PASS": "successfully moving forward",
                "FAIL": "not moving forward at this time",
                "REVIEW": "currently under manual review",
            }.get(decision, "under review")

            # Contextual tone and specific instructions based on decision
            tone_instructions = {
                "PASS": "Tone: Enthusiastic, warm, and professional. Celebrate the achievement.",
                "REVIEW": "Tone: Professional, transparent, and neutral. Explain that a person is looking at it.",
                "FAIL": "Tone: Empathetic, respectful, and encouraging. Keep the door open for future roles.",
            }.get(decision, "Tone: Professional and clear.")

            recent_exp = ""
            if experience and isinstance(experience, list):
                # Grab the first (usually most recent) experience entry
                exp = experience[0]
                role = exp.get("role")
                org = exp.get("organization")
                if role and org:
                    recent_exp = f"Most Recent Role: {role} at {org}"
                elif role:
                    recent_exp = f"Most Recent Role: {role}"
                elif org:
                    recent_exp = f"Recent Experience at: {org}"

            prompt = (
                "You are an elite executive recruiter. Write a highly personalized, professional email.\n"
                f"{tone_instructions}\n"
                "\n"
                "STRICT PROHIBITIONS:\n"
                "1. DO NOT use technical codes like 'PASS', 'FAIL', or 'REVIEW' in the email text.\n"
                "2. DO NOT use brackets [] or parentheses () for ANY reason.\n"
                "3. DO NOT use placeholder text like '[mention skill]' or '[link]'.\n"
                "4. DO NOT invent links, websites, or contact info not provided in the context.\n"
                "5. DO NOT use phrases like 'e.g.' or 'for example' followed by instructions.\n"
                "\n"
                "ONE-SHOT EXAMPLE:\n"
                "Context: Candidate: Alice, Job: Dev, Skills: Python, Docker, Result: successfully moving forward\n"
                "Output: {\"subject\": \"Exciting news regarding your Developer application\", \"body\": \"Dear Alice, We were very impressed with your background in Python and Docker. We would love to move forward...\"}\n"
                "\n"
                "CONTEXT:\n"
                f"Candidate: {candidate_name or 'Valued Candidate'}\n"
                f"Job Title: {settings.job_title}\n"
                f"Company: {settings.company_name}\n"
                f"Recruiter: {settings.recruiter_name} ({settings.recruiter_title})\n"
                f"Current Status: {friendly_status}\n"
                f"Top Skills: {', '.join(skills[:3]) if skills else 'Relevant industry experience'}\n"
                f"{recent_exp}\n"
                "\n"
                "Return JSON only with 'subject' and 'body' keys."
            )

            response = generate_json_response(
                base_url=settings.ollama_base_url,
                model=settings.notification_model,
                prompt=prompt,
                temperature=0.1,
                timeout_seconds=settings.ollama_timeout_seconds,
            )
            data = json.loads(response)
            final_subject = data.get("subject", "")
            final_body = data.get("body", "")

            # Post-processing safety net: Strip any brackets or parentheses placeholders
            # and clean up double spaces they might leave behind.
            if final_body:
                final_body = re.sub(r'\[.*?\]', '', final_body)
                final_body = re.sub(r'\(.*?\)', '', final_body)
                final_body = re.sub(r'\s{2,}', ' ', final_body).strip()
            if final_subject:
                final_subject = re.sub(r'\[.*?\]', '', final_subject)
                final_subject = re.sub(r'\(.*?\)', '', final_subject).strip()

        except (OllamaError, ValueError, json.JSONDecodeError):
            pass

    if not final_subject or not final_body:
        # Fallback to deterministic subject and Jinja2 template
        final_subject = _build_subject(decision, candidate_name)
        template_name = TEMPLATE_FILENAMES.get(decision, TEMPLATE_FILENAMES["REVIEW"])
        template_text = _load_template(template_name)
        final_body = Template(template_text).render(
            name=candidate_name or "there",
            application_id=state.get("application_id", "unknown"),
            decision=decision,
            job_title=settings.job_title,
            company_name=settings.company_name,
            recruiter_name=settings.recruiter_name,
            recruiter_title=settings.recruiter_title,
        )

    return final_subject, final_body, _wrap_in_html(final_body, settings)


@traced("notification_agent")
def notification_agent(state: ApplicationState) -> dict[str, object]:
    """Send the decision email and return the notification outcome."""
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

    subject, body, html_body = _render_notification(state, decision)
    send_result = send_email_tool.invoke(
        {
            "to_address": recipient,
            "subject": subject,
            "body": body,
            "html_body": html_body,
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
