"""LangGraph StateGraph definitions for the research pipelines.

Builds three static pipelines (threat model T-03-05 / T-04-09 -- no
runtime graph modification or user-controlled node selection):

    build_pipeline (Phase 1):
        START -> extract -> analyze -> END
    build_research_pipeline (Phase 3):
        START -> research -> signal -> END
    build_multi_agent_pipeline (Phase 4):
        START -> [fundamental, sentiment, technical] (parallel)
             -> manager -> signal -> END

Each pipeline uses a distinct TypedDict state (PipelineState,
ResearchPipelineState, or MultiAgentPipelineState). All three accept an
optional checkpointer to enable PostgreSQL state persistence between
pipeline steps.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ai_hedge_fund.graph.nodes import (
    analyze_node,
    extract_node,
    fundamental_node,
    manager_node,
    multi_agent_signal_node,
    research_node,
    sentiment_node,
    signal_node,
    technical_node,
)
from ai_hedge_fund.schemas.state import (
    MultiAgentPipelineState,
    PipelineState,
    ResearchPipelineState,
)


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


def build_multi_agent_pipeline(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build the Phase-4 multi-agent pipeline.

    Topology:
        START -> [fundamental, sentiment, technical] (parallel analysts)
              -> manager
              -> signal
              -> END

    Each parallel analyst writes to ``analyst_reports`` via the
    ``Annotated[list[dict], operator.add]`` reducer on
    ``MultiAgentPipelineState``, so LangGraph concatenates the three
    single-element lists into one 3-element list before the manager
    node executes. The manager synthesizes the reports into a
    ``ThesisOutput``; the signal node converts that thesis into a
    ``SignalOutput``.

    Graph topology is compile-time static (threat model T-04-09: no
    runtime graph modification or user-controlled node selection).
    Every node run is bounded by per-agent ``UsageLimits`` (T-04-04,
    T-04-07). Analyst-level failures propagate inside
    ``analyst_reports`` rather than crashing the pipeline, so the
    manager can still synthesize whatever reports succeeded.

    Args:
        checkpointer: Optional LangGraph checkpoint saver for durable
            state persistence. Pass a ``PostgresSaver`` in production.

    Returns:
        Compiled ``StateGraph`` ready for invocation via ``ainvoke``.
    """
    builder = StateGraph(MultiAgentPipelineState)

    # Nodes -- three parallel analysts, one manager, one signal adapter.
    builder.add_node("fundamental", fundamental_node)
    builder.add_node("sentiment", sentiment_node)
    builder.add_node("technical", technical_node)
    builder.add_node("manager", manager_node)
    builder.add_node("signal", multi_agent_signal_node)

    # Fan-out: START -> all 3 analysts in parallel.
    builder.add_edge(START, "fundamental")
    builder.add_edge(START, "sentiment")
    builder.add_edge(START, "technical")

    # Fan-in: all 3 analysts -> manager (LangGraph barriers on the reducer).
    builder.add_edge("fundamental", "manager")
    builder.add_edge("sentiment", "manager")
    builder.add_edge("technical", "manager")

    # Manager -> signal -> END (sequential tail).
    builder.add_edge("manager", "signal")
    builder.add_edge("signal", END)

    return builder.compile(checkpointer=checkpointer)
