from __future__ import annotations

import json
from pathlib import Path

from app.graph.workflow import build_workflow


def test_workflow_runs_with_stubbed_agents(monkeypatch, tmp_path: Path) -> None:
    candidate_file = tmp_path / "candidate.txt"
    candidate_file.write_text("Test Candidate", encoding="utf-8")
    monkeypatch.setattr("app.agents.extraction_agent.update_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agents.validation_agent.update_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.agents.extraction_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "name": "Test Candidate",
                "email": "test@example.com",
                "phone": None,
                "website": None,
                "skills": ["Python"],
                "experience": [{"title": "Engineer", "company": "Acme", "duration": "2 years"}],
                "education": [{"degree": "BSc", "institution": "Uni", "year": "2021"}],
                "other_details": [],
            }
        ),
    )
    monkeypatch.setattr(
        "app.agents.validation_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "is_valid": True,
                "validation_reason": "Valid"
            }
        ),
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

    assert result["decision"] == "REVIEW"
    assert result["notification_status"] == "sent"
    assert len(result["audit_log"]) == 6
