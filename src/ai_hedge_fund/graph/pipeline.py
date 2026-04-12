"""LangGraph StateGraph definitions for the research pipelines.

Builds two static pipelines (threat model T-03-05 -- no runtime graph
modification or user-controlled node selection):

    build_pipeline (Phase 1):             START -> extract -> analyze -> END
    build_research_pipeline (Phase 3):    START -> research -> signal  -> END

Each pipeline uses a distinct TypedDict state (PipelineState vs
ResearchPipelineState). Both accept an optional checkpointer to enable
PostgreSQL state persistence between pipeline steps.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ai_hedge_fund.graph.nodes import (
    analyze_node,
    extract_node,
    research_node,
    signal_node,
)
from ai_hedge_fund.schemas.state import PipelineState, ResearchPipelineState


def build_pipeline(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build the foundation pipeline: extract -> analyze.

    Creates a LangGraph StateGraph with two nodes that wrap PydanticAI
    agents. The graph is compiled and ready for invocation via ainvoke().

    Args:
        checkpointer: Optional checkpoint saver for PostgreSQL state
            persistence. Pass a PostgresSaver for durable execution.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    builder = StateGraph(PipelineState)

    builder.add_node("extract", extract_node)
    builder.add_node("analyze", analyze_node)

    builder.add_edge(START, "extract")
    builder.add_edge("extract", "analyze")
    builder.add_edge("analyze", END)

    return builder.compile(checkpointer=checkpointer)


def build_research_pipeline(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build the research pipeline: research -> signal.

    Phase-3 pipeline that takes a ticker + as_of_date and produces a thesis
    and a trade signal. The research node calls data tools to gather
    evidence and emits a ThesisOutput dict; the signal node converts that
    thesis into a SignalOutput dict. Graph topology is compile-time static
    (threat model T-03-05) and every node run is bounded by UsageLimits
    (threat model T-03-06/07 DoS).

    Args:
        checkpointer: Optional checkpoint saver for PostgreSQL state
            persistence. Pass a PostgresSaver for durable execution.

    Returns:
        Compiled StateGraph ready for invocation via ``ainvoke``.
    """
    builder = StateGraph(ResearchPipelineState)

    builder.add_node("research", research_node)
    builder.add_node("signal", signal_node)

    builder.add_edge(START, "research")
    builder.add_edge("research", "signal")
    builder.add_edge("signal", END)

    return builder.compile(checkpointer=checkpointer)
