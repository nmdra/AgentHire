from __future__ import annotations

from pathlib import Path

from app.graph.workflow import build_workflow


def test_workflow_runs_with_stubbed_agents(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "app.agents.extraction_agent.extraction_agent",
        lambda _state: {"status": "extracted", "extracted_json": {"name": "Test"}, "audit_log": []},
    )

    workflow = build_workflow()
    state = {
        "application_id": "app-1",
        "file_path": str(tmp_path / "candidate.txt"),
        "status": "processing",
        "errors": [],
        "audit_log": [],
    }

    result = workflow.invoke(state)

    assert result["decision"] == "REVIEW"
    assert result["notification_status"] == "sent"
