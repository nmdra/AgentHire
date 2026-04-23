from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import BackgroundTasks
from fastapi import UploadFile

from app.database import create_application, init_database, insert_audit_entries
from app.main import DirectEvaluationRequest, evaluate, health, logs, process_application


def _build_settings(base_dir: Path) -> SimpleNamespace:
    """Create test settings that isolate database and file writes."""
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (base_dir / "reports").mkdir(parents=True, exist_ok=True)
    settings = SimpleNamespace(
        db_path=str(base_dir / "agenthire.db"),
        uploads_dir=str(base_dir / "uploads"),
        reports_dir=str(base_dir / "reports"),
        max_upload_size_bytes=10485760,
        ollama_base_url="http://localhost:11434",
        extraction_model="smollm:360m",
        evaluation_model="gemma3:1b-it-q4_K_M",
        ollama_timeout_seconds=30.0,
        default_rubric_path=str((Path.cwd() / "rubrics" / "default_rubric.json").resolve()),
    )
    init_database(settings.db_path)
    return settings


def test_health_endpoint_reports_ok_db_and_down_ollama(monkeypatch) -> None:
    settings = _build_settings(Path("tests_runtime") / "health")
    monkeypatch.setattr("app.main.get_settings", lambda: settings)

    def raise_connect_error(*_args, **_kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.main.httpx.get", raise_connect_error)

    response = health()

    assert response == {"api": "ok", "db": "ok", "ollama": "down"}


def test_evaluate_endpoint_returns_score_and_reasoning(monkeypatch) -> None:
    settings = _build_settings(Path("tests_runtime") / "evaluate")
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.agents.evaluation_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "overall_summary": "Candidate demonstrates relevant technical capability.",
                "strengths": ["Technical skills align with the rubric"],
                "gaps": ["Experience depth could be stronger"],
            }
        ),
    )

    response = evaluate(
        DirectEvaluationRequest(
            extracted_json={
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "+94-77-123-4567",
                "website": "https://janedoe.dev",
                "skills": ["Python", "FastAPI", "SQLite"],
                "experience": [
                    {
                        "title": "Backend Engineer",
                        "company": "Acme",
                        "duration": "3 years",
                    }
                ],
                "education": [
                    {
                        "degree": "BSc Computer Science",
                        "institution": "State University",
                        "year": "2021",
                    }
                ],
                "other_details": ["AWS Certified"],
            }
        )
    )

    assert response["evaluation_score"] > 0.0
    assert "Candidate demonstrates relevant technical capability." in response["evaluation_reasoning"]
    assert len(response["criterion_breakdown"]) == 4


def test_logs_endpoint_returns_audit_entries(monkeypatch) -> None:
    settings = _build_settings(Path("tests_runtime") / "logs")
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    init_database(settings.db_path)
    application_id = create_application(settings.db_path, "candidate.txt", "uploads/candidate.txt")
    insert_audit_entries(
        settings.db_path,
        application_id,
        [
            {
                "agent_name": "evaluation_agent",
                "tool_name": "evaluation_agent",
                "input_summary": "{'application_id': 'app-1'}",
                "output_summary": "{'evaluation_score': 80.0}",
                "latency_ms": 12.5,
            }
        ],
    )

    payload = logs(application_id)

    assert len(payload) == 1
    assert payload[0]["agent_name"] == "evaluation_agent"
    assert payload[0]["tool_name"] == "evaluation_agent"


def test_process_endpoint_accepts_optional_rubric(monkeypatch) -> None:
    settings = _build_settings(Path("tests_runtime") / "process")
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    captured: dict[str, object] = {}

    def fake_process(application_id: str, file_path: str, rubric: dict[str, object] | None = None) -> None:
        captured["application_id"] = application_id
        captured["file_path"] = file_path
        captured["rubric"] = rubric

    monkeypatch.setattr("app.main._process_application", fake_process)

    rubric_payload = {
        "criteria": [
            {"name": "Technical Skills", "weight": 0.4, "description": "Skills relevance"},
            {"name": "Experience", "weight": 0.3, "description": "Work experience"},
            {"name": "Communication", "weight": 0.2, "description": "Communication clarity"},
            {"name": "Education", "weight": 0.1, "description": "Education background"},
        ],
        "pass_threshold": 75,
        "review_threshold": 60,
    }

    file_upload = UploadFile(
        filename="candidate.txt",
        file=io.BytesIO(b"Jane Doe\nEmail: jane@example.com"),
    )
    rubric_upload = UploadFile(
        filename="rubric.json",
        file=io.BytesIO(json.dumps(rubric_payload).encode("utf-8")),
    )
    background_tasks = BackgroundTasks()

    response = asyncio.run(
        process_application(background_tasks=background_tasks, file=file_upload, rubric=rubric_upload)
    )
    for task in background_tasks.tasks:
        task.func(*task.args, **task.kwargs)

    assert response["status"] == "processing"
    assert captured["application_id"] == response["application_id"]
    assert isinstance(captured["rubric"], dict)
