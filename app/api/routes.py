from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.core.config import Settings, get_settings
from app.db.repository import ApplicationRepository
from app.models.schemas import (
    ApplicationStatusResponse,
    AuditLogResponse,
    HealthResponse,
    ProcessResponse,
)
from app.services.file_storage import store_upload, validate_upload
from app.services.health import check_db, check_ollama
from app.services.pipeline import process_application

router = APIRouter()
_UPLOAD_CHUNK_SIZE = 1024 * 1024


class RubricTooLargeError(ValueError):
    pass


def _get_repo(settings: Settings) -> ApplicationRepository:
    return ApplicationRepository(settings.db_path)


def _read_upload_limited(file: UploadFile, max_size_bytes: int) -> bytes:
    total = 0
    chunks: list[bytes] = []
    while True:
        remaining = max_size_bytes - total
        if remaining < 0:
            raise RubricTooLargeError("Rubric file too large")
        if remaining == 0:
            if file.file.read(1):
                raise RubricTooLargeError("Rubric file too large")
            break
        chunk = file.file.read(min(_UPLOAD_CHUNK_SIZE, remaining))
        if not chunk:
            break
        total += len(chunk)
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(api="ok", db=check_db(settings.db_path), ollama=check_ollama(settings.ollama_base_url))


@router.post("/applications/upload", response_model=ProcessResponse)
def upload_application(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> ProcessResponse:
    try:
        validate_upload(file, settings.max_upload_size_bytes)
        path = store_upload(file, settings.uploads_dir, settings.max_upload_size_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    application_id = str(uuid.uuid4())
    repo = _get_repo(settings)
    repo.create_application(application_id, path)
    return ProcessResponse(application_id=application_id, status="uploaded")


@router.post("/applications/process", response_model=ProcessResponse)
def process_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    rubric: UploadFile | None = File(default=None),
    settings: Settings = Depends(get_settings),
) -> ProcessResponse:
    try:
        validate_upload(file, settings.max_upload_size_bytes)
        path = store_upload(file, settings.uploads_dir, settings.max_upload_size_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rubric_payload = None
    if rubric is not None:
        try:
            rubric_bytes = _read_upload_limited(rubric, settings.max_upload_size_bytes)
            rubric_payload = json.loads(rubric_bytes.decode("utf-8"))
        except RubricTooLargeError as exc:
            raise HTTPException(status_code=400, detail="Rubric file too large") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid rubric JSON") from exc

    application_id = str(uuid.uuid4())
    repo = _get_repo(settings)
    repo.create_application(application_id, path)

    email_config = {
        "resend_api_key": settings.resend_api_key,
        "resend_from_email": settings.resend_from_email,
    }
    background_tasks.add_task(
        process_application,
        repo,
        application_id,
        path,
        rubric_payload,
        settings.reports_dir,
        email_config,
        settings.retry_attempts,
    )
    return ProcessResponse(application_id=application_id, status="processing")


@router.get("/applications/{application_id}/status", response_model=ApplicationStatusResponse)
def status_endpoint(
    application_id: str, settings: Settings = Depends(get_settings)
) -> ApplicationStatusResponse:
    repo = _get_repo(settings)
    app = repo.get_application(application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationStatusResponse.model_validate(app)


@router.get("/applications/{application_id}/logs", response_model=list[AuditLogResponse])
def logs_endpoint(application_id: str, settings: Settings = Depends(get_settings)) -> list[AuditLogResponse]:
    repo = _get_repo(settings)
    if repo.get_application(application_id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    logs = repo.list_audit_logs(application_id)
    return [AuditLogResponse.model_validate(log) for log in logs]
