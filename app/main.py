"""FastAPI app entrypoint for AgentHire."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.agents.evaluation_agent import evaluate_extracted_json
from app.config import get_settings
from app.database import (
    create_application,
    get_application_logs,
    get_application_status,
    get_connection,
    init_database,
    insert_audit_entries,
    update_application,
)
from app.graph.workflow import build_workflow
from app.logger import setup_logger
from app.state import ApplicationState
from app.tools.load_rubric import validate_rubric_payload

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


class DirectEvaluationRequest(BaseModel):
    """Request payload for direct evaluation API testing."""

    extracted_json: dict[str, object] = Field(
        description="Structured applicant data produced by the extraction stage."
    )
    rubric: dict[str, object] | None = Field(
        default=None,
        description="Optional rubric override; defaults to the configured rubric file.",
    )


def _process_application(
    application_id: str,
    file_path: str,
    *,
    rubric: dict[str, object] | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> None:
    """Execute the LangGraph workflow for a saved application file."""
    settings = get_settings()
    logger.info(
        f"Starting background workflow processing for application '{application_id}'"
    )

    initial_state: ApplicationState = {
        "application_id": application_id,
        "file_path": file_path,
        "background_tasks": background_tasks,
        "status": "processing",
        "errors": [],
        "audit_log": [],
    }
    if rubric is not None:
        initial_state["rubric"] = rubric

    update_application(
        settings.db_path,
        application_id,
        {"status": "processing", "errors": []},
    )

    try:
        result: dict[str, Any] = workflow.invoke(initial_state)
        logger.info(
            f"Completed workflow processing for application '{application_id}'"
        )
    except Exception as exc:
        logger.exception(
            f"Workflow processing failed for application '{application_id}': {exc}"
        )
        update_application(
            settings.db_path,
            application_id,
            {"status": "failed", "errors": [f"workflow failed: {exc}"]},
        )
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


def _ensure_supported_application_suffix(file_name: str) -> None:
    """Validate the uploaded application suffix."""
    suffix = Path(file_name).suffix.lower()
    if suffix not in {".pdf", ".txt", ".md", ".json"}:
        raise HTTPException(status_code=400, detail="Only PDF/TXT/MD/JSON files are supported")


async def _save_application_upload(file: UploadFile) -> tuple[str, str]:
    """Persist an uploaded application file and return identifiers."""
    settings = get_settings()
    file_name = file.filename or "application.txt"
    _ensure_supported_application_suffix(file_name)

    payload = await _read_upload_with_limit(file, max_size_bytes=settings.max_upload_size_bytes)
    save_path = Path(settings.uploads_dir) / file_name
    save_path.write_bytes(payload)
    application_id = create_application(settings.db_path, file_name, str(save_path))
    return application_id, str(save_path)


async def _parse_optional_rubric_upload(rubric: UploadFile | None) -> dict[str, object] | None:
    """Read and validate an optional rubric upload."""
    if rubric is None:
        return None

    rubric_name = rubric.filename or "rubric.json"
    if Path(rubric_name).suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="Rubric file must be a JSON document")

    settings = get_settings()
    payload = await _read_upload_with_limit(rubric, max_size_bytes=settings.max_upload_size_bytes)
    try:
        parsed_payload = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Rubric file must be UTF-8 encoded") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Rubric file is not valid JSON") from exc

    try:
        validated = validate_rubric_payload(parsed_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return validated.model_dump()


@app.get("/health")
def health() -> dict[str, str]:
    """Return basic API, database, and Ollama health indicators."""
    settings = get_settings()

    try:
        with get_connection(settings.db_path) as conn:
            conn.execute("SELECT 1").fetchone()
        db_status = "ok"
    except sqlite3.Error:
        db_status = "down"

    try:
        response = httpx.get(
            f"{settings.ollama_base_url.rstrip('/')}/api/tags",
            timeout=settings.ollama_timeout_seconds,
        )
        ollama_status = "ok" if response.is_success else "down"
    except httpx.HTTPError:
        ollama_status = "down"

    return {"api": "ok", "db": db_status, "ollama": ollama_status}


@app.post("/upload")
@app.post("/applications/upload")
async def upload(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
) -> dict[str, str]:
    """Upload an application file and start async workflow processing."""
    logger.info(f"Received upload request for file '{file.filename}'")
    application_id, file_path = await _save_application_upload(file)
    background_tasks.add_task(_process_application, application_id, file_path)
    return {"application_id": application_id, "status": "processing"}


@app.post("/applications/process")
async def process_application(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    rubric: UploadFile | None = File(default=None),
) -> dict[str, str]:
    """Upload an application file and optional rubric, then start processing."""
    logger.info(f"Received process request for file '{file.filename}'")
    application_id, file_path = await _save_application_upload(file)
    rubric_payload = await _parse_optional_rubric_upload(rubric)
    background_tasks.add_task(
        _process_application,
        application_id,
        file_path,
        rubric=rubric_payload,
    )
    return {"application_id": application_id, "status": "processing"}


@app.get("/applications/{application_id}/status")
@app.get("/{application_id}/status")
def status(application_id: str) -> dict[str, Any]:
    """Get persisted status for a submitted application."""
    record = get_application_status(get_settings().db_path, application_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return record


@app.get("/applications/{application_id}/logs")
def logs(application_id: str) -> list[dict[str, Any]]:
    """Return ordered audit logs for a submitted application."""
    settings = get_settings()
    if get_application_status(settings.db_path, application_id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return get_application_logs(settings.db_path, application_id)


@app.post("/evaluate")
def evaluate(request: DirectEvaluationRequest) -> dict[str, object]:
    """Evaluate structured extracted data directly without running the full workflow."""
    settings = get_settings()
    try:
        return evaluate_extracted_json(
            request.extracted_json,
            rubric=request.rubric,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
