from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agents.evaluation_agent import evaluation_agent
from app.tools.load_rubric import load_rubric_tool
from app.tools.score_rubric import score_against_rubric_tool


@pytest.fixture
def strong_candidate() -> dict[str, object]:
    return {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+94-77-123-4567",
        "website": "https://janedoe.dev",
        "skills": ["Python", "FastAPI", "LangChain", "SQLite", "Docker"],
        "experience": [
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "duration": "3 years",
            },
            {
                "title": "Software Engineer",
                "company": "Beta Labs",
                "duration": "2 years",
            },
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


@pytest.fixture
def base_state(strong_candidate: dict[str, object]) -> dict[str, object]:
    return {
        "application_id": "app-456",
        "file_path": "uploads/candidate.txt",
        "extracted_json": strong_candidate,
        "errors": [],
        "audit_log": [],
    }


def test_load_rubric_tool_reads_default_rubric() -> None:
    rubric = load_rubric_tool.invoke({"path": "data/default_rubric.json"})

    assert "criteria" in rubric
    assert len(rubric["criteria"]) == 4
    assert rubric["pass_threshold"] == 75
    assert rubric["review_threshold"] == 60


def test_score_against_rubric_returns_weighted_total(
    strong_candidate: dict[str, object],
) -> None:
    rubric = load_rubric_tool.invoke({"path": "data/default_rubric.json"})

    result = score_against_rubric_tool.invoke(
        {"extracted_json": strong_candidate, "rubric": rubric}
    )

    assert 0.0 <= result["total_score"] <= 100.0
    assert len(result["criterion_breakdown"]) == len(rubric["criteria"])
    assert all("reasoning" in criterion for criterion in result["criterion_breakdown"])


def test_score_against_rubric_rejects_invalid_weight_sum(
    strong_candidate: dict[str, object],
) -> None:
    invalid_rubric = {
        "criteria": [
            {"name": "Technical Skills", "weight": 0.8, "description": "Skills"},
            {"name": "Experience", "weight": 0.5, "description": "Experience"},
        ],
        "pass_threshold": 75,
        "review_threshold": 60,
    }

    with pytest.raises(ValueError):
        score_against_rubric_tool.invoke(
            {"extracted_json": strong_candidate, "rubric": invalid_rubric}
        )


def test_evaluation_agent_generates_model_backed_reasoning(
    monkeypatch: pytest.MonkeyPatch, base_state: dict[str, object]
) -> None:
    monkeypatch.setattr(
        "app.agents.evaluation_agent.update_application",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.get_settings",
        lambda: SimpleNamespace(
            db_path="agenthire.db",
            default_rubric_path="data/default_rubric.json",
            evaluation_model="gemma3:1b-it-q4_K_M",
            ollama_base_url="http://localhost:11434",
            ollama_timeout_seconds=30.0,
        ),
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "overall_summary": "Strong backend-oriented profile with good technical depth.",
                "strengths": ["Strong technical stack", "Solid experience history"],
                "gaps": ["Communication evidence could be stronger"],
            }
        ),
    )

    result = evaluation_agent(base_state)

    assert result["status"] == "evaluated"
    assert result["evaluation_score"] > 0.0
    assert "Strong backend-oriented profile" in result["evaluation_reasoning"]
    assert len(result["audit_log"]) == 1


def test_evaluation_agent_falls_back_when_model_output_is_invalid(
    monkeypatch: pytest.MonkeyPatch, base_state: dict[str, object]
) -> None:
    monkeypatch.setattr(
        "app.agents.evaluation_agent.update_application",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.get_settings",
        lambda: SimpleNamespace(
            db_path="agenthire.db",
            default_rubric_path="data/default_rubric.json",
            evaluation_model="gemma3:1b-it-q4_K_M",
            ollama_base_url="http://localhost:11434",
            ollama_timeout_seconds=30.0,
        ),
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.generate_json_response",
        lambda **_kwargs: "not-json",
    )

    result = evaluation_agent(base_state)

    assert result["status"] == "evaluated"
    assert "Overall summary:" in result["evaluation_reasoning"]
    assert "Criterion breakdown:" in result["evaluation_reasoning"]


def test_evaluation_agent_is_idempotent_for_same_state(
    monkeypatch: pytest.MonkeyPatch, base_state: dict[str, object]
) -> None:
    monkeypatch.setattr(
        "app.agents.evaluation_agent.update_application",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.get_settings",
        lambda: SimpleNamespace(
            db_path="agenthire.db",
            default_rubric_path="data/default_rubric.json",
            evaluation_model="gemma3:1b-it-q4_K_M",
            ollama_base_url="http://localhost:11434",
            ollama_timeout_seconds=30.0,
        ),
    )
    monkeypatch.setattr(
        "app.agents.evaluation_agent.generate_json_response",
        lambda **_kwargs: json.dumps(
            {
                "overall_summary": "Consistent evaluation narrative.",
                "strengths": ["Technical depth"],
                "gaps": ["Needs stronger communication evidence"],
            }
        ),
    )

    first = evaluation_agent(base_state)
    second = evaluation_agent(base_state)

    assert first["evaluation_score"] == second["evaluation_score"]
    assert first["evaluation_reasoning"] == second["evaluation_reasoning"]


def test_evaluation_agent_requires_extracted_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.agents.evaluation_agent.update_application",
        lambda *_args, **_kwargs: None,
    )

    result = evaluation_agent({"application_id": "app-456", "errors": [], "audit_log": []})

    assert result["status"] == "failed"
    assert any("application_id and extracted_json are required" in error for error in result["errors"])
