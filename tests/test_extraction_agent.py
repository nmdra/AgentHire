from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.extraction_agent import extraction_agent


@pytest.fixture
def base_state(tmp_path: Path) -> dict[str, object]:
    file_path = tmp_path / "candidate.txt"
    file_path.write_text("Jane Doe\nEmail: jane@example.com\nPython, SQL", encoding="utf-8")
    return {
        "application_id": "app-123",
        "file_path": str(file_path),
        "errors": [],
        "audit_log": [],
    }


def test_extraction_success(monkeypatch: pytest.MonkeyPatch, base_state: dict[str, object]) -> None:
    monkeypatch.setattr("app.agents.extraction_agent.update_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.agents.extraction_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "+1-123-456-7890",
                "skills": ["Python", "SQL"],
                "experience": "3 years",
                "education": "BSc Computer Science",
            }
        ),
    )

    result = extraction_agent(base_state)

    assert result["status"] == "extracted"
    assert result["extracted_json"]["name"] == "Jane Doe"
    assert len(result["audit_log"]) == 1


def test_extraction_retry_once(monkeypatch: pytest.MonkeyPatch, base_state: dict[str, object]) -> None:
    monkeypatch.setattr("app.agents.extraction_agent.update_application", lambda *_args, **_kwargs: None)
    call_count = {"count": 0}
    responses = iter([
        "not-json",
        json.dumps(
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": None,
                "skills": ["Python"],
                "experience": "3 years",
                "education": "BSc",
            }
        ),
    ])
    def mock_generate_with_retry(**_kwargs: object) -> str:
        call_count["count"] += 1
        return next(responses)

    monkeypatch.setattr(
        "app.agents.extraction_agent.generate_json_response",
        mock_generate_with_retry,
    )

    result = extraction_agent(base_state)

    assert result["status"] == "extracted"
    assert result["extracted_json"]["email"] == "jane@example.com"
    assert result["extracted_json"]["phone"] is None
    assert call_count["count"] == 2


def test_extraction_failure_after_retry(monkeypatch: pytest.MonkeyPatch, base_state: dict[str, object]) -> None:
    monkeypatch.setattr("app.agents.extraction_agent.update_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agents.extraction_agent.generate_json_response", lambda **_kwargs: "still-bad")

    result = extraction_agent(base_state)

    assert result["status"] == "failed"
    assert result["errors"]


def test_unsupported_file_type(monkeypatch: pytest.MonkeyPatch, base_state: dict[str, object]) -> None:
    monkeypatch.setattr("app.agents.extraction_agent.update_application", lambda *_args, **_kwargs: None)
    state = dict(base_state)
    state["file_path"] = str(Path(str(base_state["file_path"])).with_suffix(".docx"))

    result = extraction_agent(state)

    assert result["status"] == "failed"
    assert any("Unsupported file type" in message for message in result["errors"])


def test_missing_optional_fields_default_to_null(
    monkeypatch: pytest.MonkeyPatch, base_state: dict[str, object]
) -> None:
    monkeypatch.setattr("app.agents.extraction_agent.update_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.agents.extraction_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "name": "Jane Doe",
                "skills": ["Python"],
            }
        ),
    )

    result = extraction_agent(base_state)
    extracted = result["extracted_json"]
    assert extracted["email"] is None
    assert extracted["phone"] is None
    assert extracted["experience"] is None
    assert extracted["education"] is None
