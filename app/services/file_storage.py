from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".json"}


def validate_upload(file: UploadFile, max_size_bytes: int) -> None:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type")
    if file.size and file.size > max_size_bytes:
        raise ValueError("File too large")


def store_upload(file: UploadFile, uploads_dir: str) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    unique_name = f"{uuid.uuid4()}{suffix}"
    destination = Path(uploads_dir) / unique_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = file.file.read()
    destination.write_bytes(content)
    return str(destination)
