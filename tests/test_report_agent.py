from __future__ import annotations

from pathlib import Path

from app.agents.report_agent import report_agent
from app.config import Settings


def _settings_for_reports(report_dir: Path) -> Settings:
    return Settings(
        db_path="test.db",
        uploads_dir="uploads",
        reports_dir=str(report_dir),
        max_upload_size_bytes=10_485_760,
        ollama_base_url="http://localhost:11434",
        extraction_model="smollm:360m",
        ollama_timeout_seconds=30.0,
    )


def test_report_agent_writes_reports_and_returns_text(monkeypatch, tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    monkeypatch.setattr("app.agents.report_agent.get_settings", lambda: _settings_for_reports(report_dir))

    state = {
        "application_id": "app-123",
        "decision": "PASS",
        "confidence": 0.92,
        "evaluation_score": 87.5,
        "evaluation_reasoning": "Strong technical fit.",
        "decision_reason": "Meets the pass threshold.",
        "extracted_json": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+1-555-123-4567",
            "website": "https://example.com",
            "skills": ["Python", "SQL"],
            "experience": [{"title": "Engineer", "company": "Acme", "duration": "2 years"}],
            "education": [{"degree": "BSc", "institution": "Uni", "year": "2021"}],
            "other_details": [],
        },
        "errors": [],
        "audit_log": [],
    }

    result = report_agent(state)

    applicant_path = report_dir / "app-123_applicant.md"
    internal_path = report_dir / "app-123_internal.md"

    assert result["status"] == "reported"
    assert result["report_applicant"].startswith("# Applicant Report")
    assert result["report_internal"].startswith("# Internal Report")
    assert applicant_path.exists()
    assert internal_path.exists()
    assert "PASS" in applicant_path.read_text(encoding="utf-8")
    assert "Evaluation Score" in internal_path.read_text(encoding="utf-8")


def test_report_agent_keeps_applicant_report_free_of_internal_score(monkeypatch, tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    monkeypatch.setattr("app.agents.report_agent.get_settings", lambda: _settings_for_reports(report_dir))

    state = {
        "application_id": "app-456",
        "decision": "REVIEW",
        "evaluation_score": 61.0,
        "evaluation_reasoning": "Needs recruiter review.",
        "decision_reason": "Borderline fit.",
        "extracted_json": {
            "name": "Alex Smith",
            "skills": ["Python"],
            "experience": [],
            "education": [],
        },
        "errors": [],
        "audit_log": [],
    }

    result = report_agent(state)

    applicant_report = result["report_applicant"]

    assert "61.0" not in applicant_report
    assert "Needs recruiter review" not in applicant_report
    assert "Evaluation Score" not in applicant_report


def test_report_agent_handles_minimal_state(monkeypatch, tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    monkeypatch.setattr("app.agents.report_agent.get_settings", lambda: _settings_for_reports(report_dir))

    result = report_agent({"application_id": "app-789", "errors": [], "audit_log": []})

    assert result["status"] == "reported"
    assert "Unknown" in result["report_applicant"]
    assert "n/a" in result["report_internal"]