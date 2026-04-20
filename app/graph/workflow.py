from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.nodes import (
    decision_agent_node,
    evaluation_agent_node,
    extraction_agent_node,
    human_review_node,
    notification_agent_node,
    report_agent_node,
)
from app.db.repository import ApplicationRepository
from app.models.state import ApplicationState


def _with_retries(func: Callable[[ApplicationState], dict[str, Any]], retries: int) -> Callable[[ApplicationState], dict[str, Any]]:
    def wrapped(state: ApplicationState) -> dict[str, Any]:
        last_error: Exception | None = None
        for _ in range(max(1, retries + 1)):
            try:
                return func(state)
            except Exception as exc:  # pragma: no cover
                last_error = exc
        raise RuntimeError("Node failed after retries") from last_error

    return wrapped


def build_workflow(
    repo: ApplicationRepository,
    reports_dir: str,
    smtp_config: dict[str, Any],
    retries: int = 2,
) -> Any:
    graph = StateGraph(ApplicationState)

    graph.add_node("extract", _with_retries(lambda s: extraction_agent_node(s, repo), retries))  # type: ignore[call-overload]
    graph.add_node("evaluate", _with_retries(lambda s: evaluation_agent_node(s, repo), retries))  # type: ignore[call-overload]
    graph.add_node("decide", _with_retries(lambda s: decision_agent_node(s, repo), retries))  # type: ignore[call-overload]
    graph.add_node(  # type: ignore[call-overload]
        "report",
        _with_retries(lambda s: report_agent_node(s, repo, reports_dir), retries),
    )
    graph.add_node(  # type: ignore[call-overload]
        "notify",
        _with_retries(lambda s: notification_agent_node(s, repo, smtp_config), retries),
    )
    graph.add_node("human_review", _with_retries(lambda s: human_review_node(s, repo), retries))  # type: ignore[call-overload]

    graph.set_entry_point("extract")
    graph.add_edge("extract", "evaluate")
    graph.add_edge("evaluate", "decide")
    graph.add_conditional_edges(
        "decide",
        lambda state: "REVIEW" if state.get("decision") == "REVIEW" else "NORMAL",
        {"REVIEW": "human_review", "NORMAL": "report"},
    )
    graph.add_edge("human_review", "report")
    graph.add_edge("report", "notify")
    graph.add_edge("notify", END)

    return graph.compile()
