"""LangGraph StateGraph definition for the research pipeline.

Builds a two-node pipeline: extract -> analyze.
Graph structure is compile-time static (threat model T-03-05):
    START -> extract -> analyze -> END
No runtime graph modification or user-controlled node selection.

The pipeline uses PipelineState (TypedDict) as its state type.
An optional checkpointer enables PostgreSQL state persistence
between pipeline steps.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ai_hedge_fund.graph.nodes import analyze_node, extract_node
from ai_hedge_fund.schemas.state import PipelineState


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
