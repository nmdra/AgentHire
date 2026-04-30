"""Extraction agent implementation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.database import update_application
from app.logger import setup_logger
from app.observability import traced
from app.state import ApplicationState
from app.tools.ollama import extract_first_json, generate_json_response
from app.tools.parse_json import parse_json_tool
from app.tools.parse_pdf import parse_pdf_tool
from app.tools.parse_text import parse_text_tool
from app.tools.validate_extraction import CandidateExtraction

MAX_INPUT_CHARS = 32000
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_REGEX = re.compile(r"https?://\S+")
YEAR_REGEX = re.compile(r"\b(19|20)\d{2}\b")

logger = setup_logger("extraction_agent")


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
    """Build the prompt sent to the extraction model.

    Formats the prompt according to the NuExtract template.
    """
    text = raw_text[:MAX_INPUT_CHARS]

    template = """{
    "name": null,
    "email": null,
    "phone": null,
    "website": null,
    "skills": [],
    "experience": [{"title": null, "company": null, "duration": null}],
    "education": [{"degree": null, "institution": null, "year": null}],
    "other_details": []
}"""

    prompt = f"<|input|>\n### Template:\n{template}\n### Text:\n{text}\n\n<|output|>\n"

    if correction_error:
        prompt = f"Previous response failed validation: {correction_error}\n\n" + prompt

    return prompt


def _empty_extraction_payload() -> dict[str, Any]:
    """Return the default structured extraction payload."""
    return {
        "name": None,
        "email": None,
        "phone": None,
        "website": None,
        "skills": [],
        "experience": [],
        "education": [],
        "other_details": [],
    }


def _score_extraction(payload: dict[str, Any]) -> int:
    """Return a rough completeness score for comparing extraction outputs."""
    score = 0
    if payload.get("name"):
        score += 3
    if payload.get("email"):
        score += 3
    if payload.get("phone"):
        score += 2
    if payload.get("website"):
        score += 2
    score += min(len(payload.get("skills", [])), 5)
    score += min(len(payload.get("experience", [])), 3)
    score += min(len(payload.get("education", [])), 3)
    return score


def _parse_experience_line(value: str) -> dict[str, str | None]:
    """Parse a simple free-text experience line into structured fields."""
    value = value.strip()
    match = re.match(r"(?P<title>.+?)\s+at\s+(?P<company>.+?)\s+for\s+(?P<duration>.+)", value, re.I)
    if match:
        return {
            "title": match.group("title").strip(),
            "company": match.group("company").strip(),
            "duration": match.group("duration").strip(),
        }
    return {"title": value or None, "company": None, "duration": None}


def _parse_education_line(value: str) -> dict[str, str | None]:
    """Parse a simple free-text education line into structured fields."""
    value = value.strip()
    year_match = YEAR_REGEX.search(value)
    year = year_match.group(0) if year_match else None
    cleaned = value.replace(year, "").strip(" ,-") if year else value
    return {"degree": cleaned or None, "institution": None, "year": year}


def _heuristic_extract(raw_text: str) -> dict[str, Any]:
    """Extract common resume fields deterministically from labeled text."""
    payload = _empty_extraction_payload()
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return payload

    first_line = lines[0].lstrip("\ufeff")
    if ":" not in first_line and not EMAIL_REGEX.search(first_line) and len(first_line) > 3:
        payload["name"] = first_line

    email_match = EMAIL_REGEX.search(raw_text)
    if email_match:
        payload["email"] = email_match.group(0)

    website_match = URL_REGEX.search(raw_text)
    if website_match:
        payload["website"] = website_match.group(0).rstrip(".,)")

    for line in lines:
        lowered = line.lower()

        if lowered.startswith("name:") and not payload["name"]:
            payload["name"] = line.split(":", 1)[1].strip().lstrip("\ufeff") or None
        elif lowered.startswith("email:") and not payload["email"]:
            payload["email"] = line.split(":", 1)[1].strip() or None
        elif lowered.startswith("phone:"):
            payload["phone"] = line.split(":", 1)[1].strip() or None
        elif lowered.startswith("website:") and not payload["website"]:
            payload["website"] = line.split(":", 1)[1].strip() or None
        elif lowered.startswith("skills:"):
            skills_text = line.split(":", 1)[1]
            payload["skills"] = [
                item.strip()
                for item in re.split(r"[,;/]", skills_text)
                if item.strip()
            ]
        elif lowered.startswith("experience:"):
            value = line.split(":", 1)[1].strip()
            if value:
                payload["experience"].append(_parse_experience_line(value))
        elif lowered.startswith("education:"):
            value = line.split(":", 1)[1].strip()
            if value:
                payload["education"].append(_parse_education_line(value))
        elif lowered.startswith("other details:"):
            value = line.split(":", 1)[1].strip()
            if value:
                payload["other_details"].append(value)

    return CandidateExtraction.model_validate(payload).model_dump()


def _extract_with_retry(
    raw_text: str, *, model: str, base_url: str, timeout_seconds: float, num_ctx: int
) -> dict[str, Any]:
    error: str | None = None
    max_attempts = 2
    for attempt in range(max_attempts):
        response_text = generate_json_response(
            base_url=base_url,
            model=model,
            prompt=_build_extraction_prompt(raw_text, correction_error=error),
            timeout_seconds=timeout_seconds,
            num_ctx=num_ctx,
        )
        try:
            payload = json.loads(extract_first_json(response_text))
            # Pydantic validators automatically convert "" to None (null)
            validated = CandidateExtraction.model_validate(payload)
            model_result = validated.model_dump()
            heuristic_result = _heuristic_extract(raw_text)
            if _score_extraction(heuristic_result) > _score_extraction(model_result):
                return heuristic_result
            return model_result
        except (json.JSONDecodeError, ValidationError) as exc:
            error = str(exc)
            if attempt + 1 >= max_attempts:
                break

    heuristic_result = _heuristic_extract(raw_text)
    if _score_extraction(heuristic_result) > 0:
        return heuristic_result

    raise ValueError(f"Extraction output failed validation after retry: {error}")


@traced("extraction_agent")
def extraction_agent(state: ApplicationState) -> dict[str, Any]:
    """Extract structured applicant data from uploaded file."""
    file_path = state.get("file_path")
    application_id = state.get("application_id")
    if not file_path or not application_id:
        raise ValueError("file_path and application_id are required in state")

    settings = get_settings()
    try:
        raw_text = _read_input(file_path)
        extracted = _extract_with_retry(
            raw_text,
            model=settings.extraction_model,
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
            num_ctx=settings.ollama_num_ctx,
        )
    except Exception as exc:
        logger.error(f"Extraction failed for {application_id}: {exc}")
        error_msg = str(exc)
        update_application(
            settings.db_path,
            application_id,
            {
                "status": "failed",
                "errors": state.get("errors", []) + [error_msg],
            },
        )
        return {
            "status": "failed",
            "errors": [error_msg],
        }

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
