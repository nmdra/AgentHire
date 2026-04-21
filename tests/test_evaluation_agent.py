from __future__ import annotations

import json

import pytest

from app.agents.evaluation_agent import _build_evaluation_prompt, evaluation_agent


@pytest.fixture
def evaluation_state() -> dict[str, object]:
    return {
        "application_id": "app-eval-1",
        "extracted_json": {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "skills": ["Python", "SQL"],
            "experience": [{"title": "Engineer", "company": "Acme", "duration": "3 years"}],
            "education": [{"degree": "BSc", "institution": "State U", "year": "2020"}],
            "other_details": [],
        },
        "errors": [],
        "audit_log": [],
    }


def test_evaluation_success(monkeypatch: pytest.MonkeyPatch, evaluation_state: dict[str, object]) -> None:
    monkeypatch.setattr(
        "app.agents.evaluation_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "evaluation_score": 82.0,
                "evaluation_reasoning": "Strong technical match with relevant experience.",
            }
        ),
    )

    result = evaluation_agent(evaluation_state)
    assert result["status"] == "evaluated"
    assert result["evaluation_score"] == 82.0
    assert "technical" in str(result["evaluation_reasoning"]).lower()


def test_evaluation_edge_zero_score(
    monkeypatch: pytest.MonkeyPatch, evaluation_state: dict[str, object]
) -> None:
    monkeypatch.setattr(
        "app.agents.evaluation_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {"evaluation_score": 0.0, "evaluation_reasoning": "No qualifying evidence was provided."}
        ),
    )

    result = evaluation_agent(evaluation_state)
    assert result["evaluation_score"] == 0.0


def test_evaluation_failure_missing_extracted_json() -> None:
    result = evaluation_agent({"application_id": "app-eval-2", "errors": [], "audit_log": []})
    assert result["status"] == "failed"
    assert result["errors"]


def test_evaluation_prompt_includes_schema() -> None:
    prompt = _build_evaluation_prompt({"extracted_json": {"name": "Jane"}})
    assert '"evaluation_score"' in prompt
    assert '"evaluation_reasoning"' in prompt


def test_evaluation_masks_email_in_audit_log(
    monkeypatch: pytest.MonkeyPatch, evaluation_state: dict[str, object]
) -> None:
    monkeypatch.setattr(
        "app.agents.evaluation_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "evaluation_score": 65.0,
                "evaluation_reasoning": "Reach out to jane@example.com for verification.",
            }
        ),
    )

    result = evaluation_agent(evaluation_state)
    entry = result["audit_log"][0]
    output_summary = str(entry.get("output_summary", ""))
    assert "jane@" not in output_summary
    assert "****@" in output_summary
