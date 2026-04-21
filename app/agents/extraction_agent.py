"""Extraction agent implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.database import update_application
from app.agents.personas import EXTRACTION_PERSONA, build_structured_prompt
from app.observability import traced
from app.state import ApplicationState
from app.tools.ollama import generate_json_response
from app.tools.parse_json import parse_json_tool
from app.tools.parse_pdf import parse_pdf_tool
from app.tools.parse_text import parse_text_tool
from app.tools.validate_extraction import CandidateExtraction

MAX_INPUT_CHARS = 32000


def _strip_markdown_json_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if not lines:
        return stripped
    if lines[-1].strip() != "```":
        return stripped

    body = lines[1:-1]
    if lines[0].strip().lower() in {"```json", "```"}:
        return "\n".join(body).strip()
    return stripped


def _read_input(file_path: str) -> str:
    extension = Path(file_path).suffix.lower()
    if extension == ".pdf":
        return str(parse_pdf_tool.invoke({"path": file_path}))
    if extension in {".txt", ".md"}:
        return str(parse_text_tool.invoke({"path": file_path}))
    if extension == ".json":
        return str(parse_json_tool.invoke({"path": file_path}))
    raise ValueError("Unsupported file type. Use PDF, TXT, MD, or JSON")


def _build_extraction_prompt(raw_text: str, correction_error: str | None = None) -> str:
    task = (
        "Extract applicant details from the provided text into the exact structured JSON schema."
    )
    if correction_error:
        task = f"{task}\nPrevious response failed validation: {correction_error}"
    context = f"document_text:\n{raw_text[:MAX_INPUT_CHARS]}"
    output = (
        "Return JSON only with exactly these keys:\n"
        '{\n'
        '  "name": string or null,\n'
        '  "email": string or null,\n'
        '  "phone": string or null,\n'
        '  "website": string or null,\n'
        '  "skills": [string, ...],\n'
        '  "experience": [{"title": string or null, "company": string or null, "duration": string or null}, ...],\n'
        '  "education": [{"degree": string or null, "institution": string or null, "year": string or null}, ...],\n'
        '  "other_details": [string, ...]\n'
        '}'
    )
    return build_structured_prompt(
        persona=EXTRACTION_PERSONA,
        task=task,
        context=context,
        output=output,
    )


def _extract_with_retry(
    raw_text: str, *, model: str, base_url: str, timeout_seconds: float
) -> dict[str, Any]:
    error: str | None = None
    max_attempts = 2
    for attempt in range(max_attempts):
        response_text = generate_json_response(
            base_url=base_url,
            model=model,
            prompt=_build_extraction_prompt(raw_text, correction_error=error),
            temperature=0.0,
            top_p=0.1,
            timeout_seconds=timeout_seconds,
        )
        try:
            payload = json.loads(_strip_markdown_json_fences(response_text))
            validated = CandidateExtraction.model_validate(payload)
            return validated.model_dump()
        except (json.JSONDecodeError, ValidationError) as exc:
            error = str(exc)
            if attempt + 1 >= max_attempts:
                break

    raise ValueError(f"Extraction output failed validation after retry: {error}")


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
