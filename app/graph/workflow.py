"""LangGraph workflow wiring for AgentHire."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.decision_agent import decision_agent
from app.agents.evaluation_agent import evaluation_agent
from app.agents.extraction_agent import extraction_agent
from app.agents.notification_agent import notification_agent
from app.agents.report_agent import report_agent
from app.state import ApplicationState


def build_workflow():
    """Compile and return the Phase 1 linear workflow graph."""
    graph = StateGraph(ApplicationState)
    graph.add_node("extract", extraction_agent)
    graph.add_node("evaluate", evaluation_agent)
    graph.add_node("decide", decision_agent)
    graph.add_node("report", report_agent)
    graph.add_node("notify", notification_agent)

    graph.add_edge(START, "extract")
    graph.add_edge("extract", "evaluate")
    graph.add_edge("evaluate", "decide")
    graph.add_edge("decide", "report")
    graph.add_edge("report", "notify")
    graph.add_edge("notify", END)

    return graph.compile()
