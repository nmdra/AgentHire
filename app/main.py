"""FastAPI app entrypoint for AgentHire."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile

from app.config import get_settings
from app.database import (
    create_application,
    get_application_status,
    init_database,
    insert_audit_entries,
    update_application,
)
from app.graph.workflow import build_workflow
from app.state import ApplicationState
from app.logger import setup_logger

logger = setup_logger("api")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize required runtime artifacts."""
    settings = get_settings()
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.reports_dir).mkdir(parents=True, exist_ok=True)
    init_database(settings.db_path)
    yield


app = FastAPI(title="AgentHire Phase 1", lifespan=lifespan)
workflow = build_workflow()


def _process_application(application_id: str, file_path: str) -> None:
    settings = get_settings()
    logger.info(f"Starting background workflow processing for application '{application_id}'")
    initial_state: ApplicationState = {
        "application_id": application_id,
        "file_path": file_path,
        "status": "processing",
        "errors": [],
        "audit_log": [],
    }

    update_application(settings.db_path, application_id, {"status": "processing", "errors": []})
    
    try:
        result: dict[str, Any] = workflow.invoke(initial_state)
        logger.info(f"Completed workflow processing for application '{application_id}'")
    except Exception as exc:
        logger.exception(f"Workflow processing failed for application '{application_id}': {exc}")
        return

    fields_to_persist = {
        key: result.get(key)
        for key in [
            "status",
            "extracted_json",
            "evaluation_score",
            "evaluation_reasoning",
            "decision",
            "confidence",
            "decision_reason",
            "report_applicant",
            "report_internal",
            "notification_status",
            "errors",
        ]
        if key in result
    }

    update_application(settings.db_path, application_id, fields_to_persist)
    insert_audit_entries(settings.db_path, application_id, list(result.get("audit_log", [])))


async def _read_upload_with_limit(
    file: UploadFile, *, max_size_bytes: int, chunk_size: int = 1024 * 1024
) -> bytes:
    """Read upload in chunks and enforce maximum size."""
    total = 0
    chunks: list[bytes] = []
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size_bytes:
            raise HTTPException(status_code=413, detail="File exceeds maximum allowed size")
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/upload")
async def upload(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
) -> dict[str, str]:
    """Upload an application file and start async workflow processing."""
    logger.info(f"Received upload request for file '{file.filename}'")
    settings = get_settings()

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".txt", ".md", ".json"}:
        raise HTTPException(status_code=400, detail="Only PDF/TXT/MD/JSON files are supported")

    payload = await _read_upload_with_limit(
        file, max_size_bytes=settings.max_upload_size_bytes
    )

    temp_name = file.filename or "application.txt"
    save_path = Path(settings.uploads_dir) / temp_name
    save_path.write_bytes(payload)

    application_id = create_application(settings.db_path, temp_name, str(save_path))

    background_tasks.add_task(_process_application, application_id, str(save_path))

    return {"application_id": application_id, "status": "processing"}


@app.get("/{application_id}/status")
def status(application_id: str) -> dict[str, Any]:
    """Get persisted status for a submitted application."""
    record = get_application_status(get_settings().db_path, application_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return record
