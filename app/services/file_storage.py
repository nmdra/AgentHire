from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".json"}
_UPLOAD_CHUNK_SIZE = 1024 * 1024


def validate_upload(file: UploadFile, max_size_bytes: int) -> None:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type")

    try:
        current_position = file.file.tell()
        try:
            file.file.seek(0, 2)
            total_size = file.file.tell()
        finally:
            file.file.seek(current_position)
    except (AttributeError, OSError):
        return

    if total_size > max_size_bytes:
        raise ValueError("File too large")
def store_upload(file: UploadFile, uploads_dir: str, max_size_bytes: int) -> str:
    suffix = Path(file.filename or "").suffix.lower()
    unique_name = f"{uuid.uuid4()}{suffix}"
    destination = Path(uploads_dir) / unique_name
    destination.parent.mkdir(parents=True, exist_ok=True)

    total_size = 0
    try:
        with destination.open("wb") as output_file:
            while True:
                chunk = file.file.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size_bytes:
                    raise ValueError("File too large")
                output_file.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return str(destination)
