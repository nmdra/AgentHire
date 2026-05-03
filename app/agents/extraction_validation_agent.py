"""Extraction Validation agent using Functional Orchestration Pattern."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.agents.personas import EXTRACTION_VALIDATION_PERSONA, build_structured_prompt
from app.config import get_settings
from app.database import update_application
from app.logger import setup_logger
from app.observability import traced
from app.state import ApplicationState
from app.tools.email_tool import send_email_tool
from app.tools.ollama import extract_first_json, generate_json_response

logger = setup_logger("extraction_validation_agent")
GENERIC_NAME_VALUES = {"user", "candidate", "unknown", "n/a", "na", "none"}
EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

class ValidationDecision(BaseModel):
    """The structured decision output from the model."""
    is_valid: bool = Field(description="True if the candidate name and email are present and valid.")
    reason: str | None = Field(default="No specific reason provided.", description="Step-by-step reasoning for the decision.")
    email_subject: str | None = Field(None, description="A professional subject line for the notification email.")
    email_body: str | None = Field(None, description="A concise HTML body for the notification email.")

    @field_validator("reason", mode="before")
    @classmethod
    def validate_reason(cls, v: Any) -> str:
        if v is None or v == "":
            return "No specific reason provided."
        return str(v)


def _normalize_text(value: object) -> str:
    """Normalize optional state values for deterministic validation."""
    if value is None:
        return ""
    return str(value).strip().lstrip("\ufeff")


def _is_generic_name(name: str) -> bool:
    """Return true when the extracted name is obviously placeholder text."""
    lowered = name.lower()
    if lowered in GENERIC_NAME_VALUES:
        return True
    if len(name) < 3:
        return True
    if "@" in name:
        return True
    return False


def _has_real_identity(extracted_json: dict[str, Any]) -> bool:
    """Check whether the extracted payload has a real name and email."""
    name = _normalize_text(extracted_json.get("name"))
    email = _normalize_text(extracted_json.get("email"))
    if not name or _is_generic_name(name):
        return False
    if not email or not EMAIL_REGEX.match(email):
        return False
    return True

@traced("extraction_validation_agent")
def extraction_validation_agent(state: ApplicationState) -> dict[str, Any]:
    """Audit extraction and execute notifications deterministically."""
    application_id = state.get("application_id")
    extracted_json = state.get("extracted_json")
    
    if not application_id or not extracted_json:
        raise ValueError("application_id and extracted_json are required in state")

    settings = get_settings()

    if not isinstance(extracted_json, dict):
        raise ValueError("extracted_json must be a dictionary")

    # Guard valid extractions deterministically so the model cannot falsely reject them.
    if _has_real_identity(extracted_json):
        decision = ValidationDecision(
            is_valid=True,
            reason="Name and email are present and appear valid.",
        )
        status = "validated"
        update_application(
            settings.db_path,
            application_id,
            {
                "status": status,
                "errors": state.get("errors", []),
            },
        )
        return {
            "status": status,
            "is_valid": True,
            "validation_reason": decision.reason,
            "errors": [],
        }
    
    # 1. Build a strict template-based prompt
    task = (
        "Audit the extracted JSON data.\n"
        "STEPS:\n"
        "1. Identify if 'name' and 'email' are present and real (not null or 'user').\n"
        "2. Decide if the extraction is valid.\n"
        "3. If invalid, generate a professional 'email_subject' and HTML 'email_body'."
    )
    
    template = {
        "is_valid": "boolean",
        "reason": "string",
        "email_subject": "string or null",
        "email_body": "string (HTML) or null"
    }
    
    prompt = build_structured_prompt(
        persona=EXTRACTION_VALIDATION_PERSONA,
        task=task,
        context=json.dumps(extracted_json, indent=2),
        output=f"CRITICAL: Return ONLY a valid JSON object. Do not include any other text. Template:\n{json.dumps(template, indent=2)}"
    )
    
    try:
        # 2. Single-Turn Intelligence (Model Reasoning)
        response_text = generate_json_response(
            base_url=settings.ollama_base_url,
            model=settings.validation_model,
            prompt=prompt,
            temperature=0.0,  # Locked for max determinism
            num_ctx=settings.ollama_num_ctx,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
        
        # Parse result into our deterministic schema
        payload = json.loads(extract_first_json(response_text))
        
        # Handle the case where the model might still use validation_reason
        if "validation_reason" in payload and ("reason" not in payload or payload["reason"] is None):
            payload["reason"] = payload.pop("validation_reason")
            
        decision = ValidationDecision.model_validate(payload)
        
        # 3. Deterministic Action (Python Execution)
        if not decision.is_valid:
            logger.info("EXTRACTION NOTIFY: Validation failed. Triggering notification.")
            
            # Prepare metadata for the email
            email_metadata = {
                "Application ID": application_id,
                "CV Filename": os.path.basename(state.get("file_path", "Unknown")),
                "Validation Reason": decision.reason
            }
            
            email_params = {
                "to_address": settings.reviewer_email,
                "subject": decision.email_subject or f"Validation Alert: {application_id}",
                "html_body": decision.email_body or f"<p>Validation failed for application {application_id}.</p>",
                "attachment_path": state.get("file_path"),
                "metadata": email_metadata
            }
            
            # Utilize FastAPI BackgroundTasks if available
            bt = state.get("background_tasks")
            if bt:
                logger.info("Queuing email via FastAPI BackgroundTasks.")
                bt.add_task(send_email_tool.invoke, email_params)
            else:
                logger.info("Executing email tool synchronously (no BackgroundTasks in state).")
                send_email_tool.invoke(email_params)
            
    except Exception as exc:
        logger.error(f"Validation Agent Error: {exc}")
        decision = ValidationDecision(is_valid=False, reason="System error during validation")
        # Enforce safety email on system error; exception details are logged server-side only
        try:
            email_params = {
                "to_address": settings.reviewer_email,
                "subject": "System Error: Extraction Validation",
                "body": f"Validation failed for application {application_id}. Check server logs for details.",
                "attachment_path": state.get("file_path")
            }

            bt = state.get("background_tasks")
            if bt:
                bt.add_task(send_email_tool.invoke, email_params)
            else:
                send_email_tool.invoke(email_params)
        except Exception as e2:
            logger.error(f"Failed to send error notification email: {e2}")

    # 4. Finalize State
    status = "validated" if decision.is_valid else "failed"
    update_application(
        settings.db_path,
        application_id,
        {
            "status": status,
            "errors": state.get("errors", []) + ([f"Validation failed: {decision.reason}"] if not decision.is_valid else []),
        },
    )

    return {
        "status": status,
        "is_valid": decision.is_valid,
        "validation_reason": decision.reason,
        "errors": [f"Validation failed: {decision.reason}"] if not decision.is_valid else []
    }
