"""Extraction agent implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.database import update_application
from app.observability import traced
from app.state import ApplicationState
from app.tools.ollama import generate_json_response
from app.tools.parse_json import parse_json_tool
from app.tools.parse_pdf import parse_pdf_tool
from app.tools.parse_text import parse_text_tool
from app.tools.validate_extraction import CandidateExtraction

MAX_INPUT_CHARS = 32000


def _read_input(file_path: str) -> str:
    extension = Path(file_path).suffix.lower()
    if extension == ".pdf":
        return str(parse_pdf_tool.invoke({"path": file_path}))
    if extension in {".txt", ".md"}:
        return str(parse_text_tool.invoke({"path": file_path}))
    if extension == ".json":
        return str(parse_json_tool.invoke({"path": file_path}))
    raise ValueError("Unsupported file type. Use PDF, TXT, MD, or JSON")


def _build_prompt(raw_text: str, correction_error: str | None = None) -> str:
    instruction = (
        "Extract applicant details as strict JSON with keys: "
        "name, email, phone, skills (array), experience, education. "
        "Return JSON only and include all keys."
    )
    if correction_error:
        instruction = f"{instruction}\nPrevious response failed validation: {correction_error}"
    return f"{instruction}\n\nApplication:\n{raw_text[:MAX_INPUT_CHARS]}"


def _extract_with_retry(
    raw_text: str, *, model: str, base_url: str, timeout_seconds: float
) -> dict[str, Any]:
    error: str | None = None
    max_attempts = 2
    for attempt in range(max_attempts):
        response_text = generate_json_response(
            base_url=base_url,
            model=model,
            prompt=_build_prompt(raw_text, correction_error=error),
            temperature=0.0,
            timeout_seconds=timeout_seconds,
        )
        try:
            payload = json.loads(response_text)
            validated = CandidateExtraction.model_validate(payload)
            return validated.model_dump()
        except (json.JSONDecodeError, ValidationError) as exc:
            error = str(exc)
            if attempt + 1 >= max_attempts:
                raise ValueError(
                    f"Extraction output failed validation after retry: {error}"
                ) from exc

    raise ValueError("Extraction output failed validation after retry")


@traced("extraction_agent")
def extraction_agent(state: ApplicationState) -> dict[str, Any]:
    """Extract structured applicant data from uploaded file."""
    file_path = state.get("file_path")
    application_id = state.get("application_id")
    if not file_path or not application_id:
        raise ValueError("file_path and application_id are required in state")

    settings = get_settings()
    raw_text = _read_input(file_path)
    extracted = _extract_with_retry(
        raw_text,
        model=settings.extraction_model,
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_timeout_seconds,
    )

    update_application(
        settings.db_path,
        application_id,
        {
            "status": "extracted",
            "extracted_json": extracted,
            "errors": state.get("errors", []),
        },
    )

    return {
        "status": "extracted",
        "extracted_json": extracted,
    }
