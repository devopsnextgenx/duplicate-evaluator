"""LangGraph StateGraph construction for the duplicate evaluator agent."""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from duplicate_evaluator.agent.nodes import (
    batch_node,
    cross_quality_llm_node,
    llm_node,
    merge_node,
    scan_node,
)
from duplicate_evaluator.models.file_entry import AnalysisMode
from duplicate_evaluator.models.state import AgentState

logger = logging.getLogger(__name__)


def _route_after_scan(state: AgentState) -> str:
    """Choose next node after scan based on mode and error status."""
    if state.get("error"):
        logger.warning("Routing to END after scan_node error: %s", state["error"])
        return "end_with_error"
    if state["mode"] == AnalysisMode.CROSS_QUALITY:
        return "cross_quality_llm_node"
    return "batch_node"


def _route_after_batch(state: AgentState) -> str:
    if state.get("error"):
        return "end_with_error"
    return "llm_node"


def _end_with_error(state: AgentState) -> dict:
    """Terminal node when an unrecoverable error occurs."""
    logger.error("Agent terminated with error: %s", state.get("error"))
    return {}


def build_graph() -> StateGraph:
    """Build and compile the LangGraph agent graph."""
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("scan_node", scan_node)
    graph.add_node("batch_node", batch_node)
    graph.add_node("llm_node", llm_node)
    graph.add_node("cross_quality_llm_node", cross_quality_llm_node)
    graph.add_node("merge_node", merge_node)
    graph.add_node("end_with_error", _end_with_error)

    # Entry point
    graph.add_edge(START, "scan_node")

    # Conditional routing after scan
    graph.add_conditional_edges(
        "scan_node",
        _route_after_scan,
        {
            "batch_node": "batch_node",
            "cross_quality_llm_node": "cross_quality_llm_node",
            "end_with_error": "end_with_error",
        },
    )

    # Within-folder path
    graph.add_conditional_edges(
        "batch_node",
        _route_after_batch,
        {
            "llm_node": "llm_node",
            "end_with_error": "end_with_error",
        },
    )
    graph.add_edge("llm_node", "merge_node")

    # Cross-quality path
    graph.add_edge("cross_quality_llm_node", "merge_node")

    # Merge → END
    graph.add_edge("merge_node", END)
    graph.add_edge("end_with_error", END)

    compiled = graph.compile()
    logger.info("LangGraph agent graph compiled successfully")
    return compiled


# Singleton compiled graph
agent_graph = build_graph()
