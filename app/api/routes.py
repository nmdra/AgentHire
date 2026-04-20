from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.core.config import Settings, get_settings
from app.db.repository import ApplicationRepository
from app.models.schemas import AuditLogResponse, HealthResponse, ProcessResponse
from app.services.file_storage import store_upload, validate_upload
from app.services.health import check_db, check_ollama
from app.services.pipeline import process_application

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_repo(settings: Settings) -> ApplicationRepository:
    return ApplicationRepository(settings.db_path)


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
        path = store_upload(file, settings.uploads_dir)
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
        path = store_upload(file, settings.uploads_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rubric_payload = None
    if rubric is not None:
        try:
            rubric_payload = json.loads(rubric.file.read().decode("utf-8"))
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


@router.get("/applications/{application_id}/status")
def status_endpoint(
    application_id: str, settings: Settings = Depends(get_settings)
) -> dict[str, object]:
    repo = _get_repo(settings)
    app = repo.get_application(application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.get("/applications/{application_id}/logs", response_model=list[AuditLogResponse])
def logs_endpoint(application_id: str, settings: Settings = Depends(get_settings)) -> list[AuditLogResponse]:
    repo = _get_repo(settings)
    if repo.get_application(application_id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    logs = repo.list_audit_logs(application_id)
    return [AuditLogResponse.model_validate(log) for log in logs]
