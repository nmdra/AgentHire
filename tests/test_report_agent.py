from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.report_agent import _build_report_prompt, report_agent


@pytest.fixture
def report_state() -> dict[str, object]:
    return {
        "application_id": "app-report-1",
        "decision": "REVIEW",
        "decision_reason": "Needs additional verification.",
        "evaluation_score": 68.0,
        "evaluation_reasoning": "Good baseline with some gaps.",
        "extracted_json": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "skills": ["Python"],
            "other_details": ["AWS Certified"],
        },
        "errors": [],
        "audit_log": [],
    }


def test_report_success(monkeypatch: pytest.MonkeyPatch, report_state: dict[str, object]) -> None:
    class DummyWriter:
        @staticmethod
        def invoke(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {}

    monkeypatch.setattr(
        "app.agents.report_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "report_applicant": "# Applicant Report\n\nYour application is under review.",
                "report_internal": "# Internal Report\n\n- Decision: REVIEW",
            }
        ),
    )
    monkeypatch.setattr("app.agents.report_agent.write_reports_tool", DummyWriter())

    result = report_agent(report_state)
    assert result["status"] == "reported"
    assert "# Applicant Report" in str(result["report_applicant"])
    assert "# Internal Report" in str(result["report_internal"])


def test_report_writes_markdown_files(
    monkeypatch: pytest.MonkeyPatch, report_state: dict[str, object], tmp_path: Path
) -> None:
    class DummySettings:
        ollama_base_url = "http://localhost:11434"
        report_model = "gemma3:1b-it-q4_K_M"
        ollama_timeout_seconds = 30.0
        reports_dir = str(tmp_path)

    monkeypatch.setattr("app.agents.report_agent.get_settings", lambda: DummySettings())
    monkeypatch.setattr(
        "app.agents.report_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "report_applicant": "# Applicant Report\n\nHello.",
                "report_internal": "# Internal Report\n\nDetails.",
            }
        ),
    )

    result = report_agent({**report_state, "application_id": "app-report-2"})
    assert result["status"] == "reported"
    assert (tmp_path / "app-report-2_applicant.md").exists()
    assert (tmp_path / "app-report-2_internal.md").exists()


def test_report_failure_missing_decision() -> None:
    result = report_agent({"application_id": "app-report-3", "errors": [], "audit_log": []})
    assert result["status"] == "failed"
    assert result["errors"]


def test_report_prompt_includes_markdown_contract() -> None:
    prompt = _build_report_prompt({"decision": "PASS"})
    assert "markdown" in prompt.lower()
    assert '"report_applicant"' in prompt
    assert '"report_internal"' in prompt


def test_report_masks_email_in_audit_log(
    monkeypatch: pytest.MonkeyPatch, report_state: dict[str, object]
) -> None:
    class DummyWriter:
        @staticmethod
        def invoke(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {}

    monkeypatch.setattr(
        "app.agents.report_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "report_applicant": "Please contact jane@example.com for follow-up.",
                "report_internal": "Internal note with jane@example.com reference.",
            }
        ),
    )
    monkeypatch.setattr("app.agents.report_agent.write_reports_tool", DummyWriter())

    result = report_agent(report_state)
    output_summary = str(result["audit_log"][0].get("output_summary", ""))
    assert "jane@" not in output_summary
    assert "****@" in output_summary
