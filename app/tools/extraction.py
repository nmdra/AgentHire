from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz

from app.models.schemas import ExtractedApplication


def parse_pdf_tool(file_path: str) -> str:
    """Extract raw text from a PDF file using PyMuPDF."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected .pdf, got {path.suffix}")
    doc = fitz.open(file_path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def read_text_tool(file_path: str) -> str:
    """Read UTF-8 text from a plain text file."""
    return Path(file_path).read_text(encoding="utf-8")


def read_json_tool(file_path: str) -> dict[str, Any]:
    """Read JSON from disk and return dictionary."""
    data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON file must contain a JSON object")
    return data


def _extract_list_section(pattern: str, text: str) -> list[str]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return []
    values = [part.strip(" -\t") for part in re.split(r",|;|\n", match.group(1))]
    return [v for v in values if v]


def _extract_simple(text: str, label: str) -> str | None:
    m = re.search(rf"{label}\s*:\s*(.+)", text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else None


def extract_application_from_text(text: str) -> dict[str, Any]:
    """Extract application fields from unstructured text using deterministic regex rules."""
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    phone_match = re.search(r"\+?[0-9][0-9\-\s]{7,}[0-9]", text)
    website_match = re.search(r"https?://[^\s]+", text)

    payload: dict[str, Any] = {
        "name": _extract_simple(text, "name"),
        "email": email_match.group(0) if email_match else _extract_simple(text, "email"),
        "phone": phone_match.group(0) if phone_match else _extract_simple(text, "phone"),
        "website": website_match.group(0) if website_match else _extract_simple(text, "website"),
        "skills": _extract_list_section(r"skills\s*:\s*(.+)", text),
        "experience": _extract_list_section(r"experience\s*:\s*(.+)", text),
        "education": _extract_list_section(r"education\s*:\s*(.+)", text),
    }
    model = ExtractedApplication.model_validate(payload)
    return model.model_dump()


def validate_json_schema_tool(data: dict[str, Any]) -> dict[str, Any]:
    """Validate extracted JSON against strict schema."""
    return ExtractedApplication.model_validate(data).model_dump()


def extract_application_from_file(file_path: str) -> dict[str, Any]:
    """Extract and validate application data from pdf/txt/json inputs."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = parse_pdf_tool(file_path)
        return extract_application_from_text(text)
    if suffix in {".txt", ".md"}:
        text = read_text_tool(file_path)
        return extract_application_from_text(text)
    if suffix == ".json":
        return validate_json_schema_tool(read_json_tool(file_path))
    raise ValueError("Unsupported file type; only .pdf, .txt, .md, .json are allowed")
