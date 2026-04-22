"""Validation agent implementation."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from app.agents.personas import VALIDATION_PERSONA, build_structured_prompt
from app.config import get_settings
from app.database import update_application
from app.observability import traced
from app.state import ApplicationState
from app.tools.ollama import extract_first_json, generate_json_response


class ValidationOutput(BaseModel):
    is_valid: bool
    validation_reason: str


def _build_validation_prompt(extracted_json: dict[str, Any]) -> str:
    """Build the prompt sent to the validation model."""
    task = (
        "Audit the provided JSON and decide if it is valid based on these strict steps:\n"
        "1. Check the 'name' field. If it is null, 'Unknown', or 'user', is_valid = false.\n"
        "2. Check the 'email' field. If it is null or empty, is_valid = false.\n"
        "3. If both are present and real, is_valid = true.\n"
        "Reason Step-by-Step, but only output the final JSON."
    )
    context = json.dumps(extracted_json, indent=2)
    output = "JSON result: {'is_valid': bool, 'validation_reason': 'short explanation'}"
    
    return build_structured_prompt(
        persona=VALIDATION_PERSONA,
        task=task,
        context=context,
        output=output,
    )


def _validate_with_retry(
    prompt: str, *, model: str, base_url: str, timeout_seconds: float, num_ctx: int
) -> ValidationOutput:
    error: str | None = None
    max_attempts = 2
    for attempt in range(max_attempts):
        current_prompt = prompt
        if error:
            current_prompt = f"Previous response failed validation: {error}\n\n{prompt}"
            
        response_text = generate_json_response(
            base_url=base_url,
            model=model,
            prompt=current_prompt,
            timeout_seconds=timeout_seconds,
            num_predict=150,
            num_ctx=num_ctx,
            temperature=0.0,
        )
        try:
            payload = json.loads(extract_first_json(response_text))
            return ValidationOutput.model_validate(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            error = str(exc)
            if attempt + 1 >= max_attempts:
                break

    raise ValueError(f"Validation output failed format checks after retry: {error}")


@traced("validation_agent")
def validation_agent(state: ApplicationState) -> dict[str, Any]:
    """Validate extracted JSON to ensure critical fields are present."""
    application_id = state.get("application_id")
    extracted_json = state.get("extracted_json")
    
    if not application_id or not extracted_json:
        raise ValueError("application_id and extracted_json are required in state")

    settings = get_settings()
    prompt = _build_validation_prompt(extracted_json)
    
    try:
        validated = _validate_with_retry(
            prompt,
            model=settings.validation_model,
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
            num_ctx=settings.ollama_num_ctx,
        )
        is_valid = validated.is_valid
        reason = validated.validation_reason
    except Exception as exc:
        is_valid = False
        reason = f"Validation failed due to error: {exc}"
        
    status = "validated" if is_valid else "validation_failed"
    errors = state.get("errors", [])
    new_errors = []
    if not is_valid:
        new_errors = [f"Validation failed: {reason}"]
        
    update_application(
        settings.db_path,
        application_id,
        {
            "status": status,
            "errors": errors + new_errors,
        },
    )

    result: dict[str, Any] = {
        "status": status,
        "is_valid": is_valid,
        "validation_reason": reason,
    }
    
    if new_errors:
        result["errors"] = new_errors
        
    return result
