from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.graph.workflow import build_workflow


def test_workflow_runs_with_stubbed_agents(monkeypatch, tmp_path: Path) -> None:
    candidate_file = tmp_path / "candidate.txt"
    candidate_file.write_text("Test Candidate", encoding="utf-8")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "noreply@agenthire.com")
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr("app.agents.extraction_agent.update_application", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(
        "app.agents.extraction_agent.update_application", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "app.agents.extraction_validation_agent.update_application",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.update_application", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.get_settings",
        lambda: SimpleNamespace(
            db_path="agenthire.db",
            default_rubric_path="data/default_rubric.json",
            ollama_base_url="http://localhost:11434",
            evaluation_model="gemma3:1b-it-q4_K_M",
            ollama_timeout_seconds=120,
        ),
    )
    monkeypatch.setattr(
        "app.agents.decision_agent.generate_decision_explanation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.agents.extraction_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "name": "Test Candidate",
                "email": "test@example.com",
                "phone": None,
                "website": None,
                "skills": ["Python"],
                "experience": [
                    {
                        "title": "Engineer",
                        "company": "Acme",
                        "duration": "2 years",
                    }
                ],
                "education": [
                    {"degree": "BSc", "institution": "Uni", "year": "2021"}
                ],
                "other_details": [],
            }
        ),
    )
    monkeypatch.setattr("resend.Emails.send", lambda payload: {"id": "mock-id-123"})
    monkeypatch.setattr(
        "app.agents.extraction_validation_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "is_valid": True,
                "reason": "Valid extraction",
                "email_subject": None,
                "email_body": None,
            }
        ),
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "overall_summary": "Candidate shows balanced technical capability.",
                "strengths": ["Technical skills are relevant"],
                "gaps": ["Communication evidence is moderate"],
            }
        ),
    )
    monkeypatch.setattr(
        "app.agents.report_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "report_title": "Application Evaluation Report",
                "report_summary": "Candidate evaluated successfully.",
                "recommendation": "Do not advance",
            }
        ),
    )
    monkeypatch.setattr(
        "app.agents.notification_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "subject": "Your application update",
                "body": "Thank you for your application. We will not be moving forward.",
            }
        ),
    )
    monkeypatch.setattr(
        "app.agents.report_agent.update_application",
        lambda *_args, **_kwargs: None,
    )

    workflow = build_workflow()
    state = {
        "application_id": "app-1",
        "file_path": str(candidate_file),
        "status": "processing",
        "errors": [],
        "audit_log": [],
    }

    result = workflow.invoke(state)

    assert result["status"] == "completed"
    assert result["decision"] == "FAIL"
    assert result["notification_status"] == "sent"
    assert result["is_valid"] is True
    assert result["evaluation_score"] > 0.0
    assert len(result["audit_log"]) == 6
