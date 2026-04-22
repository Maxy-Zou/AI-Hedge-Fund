"""LangGraph StateGraph definitions for the research pipelines.

Builds four static pipelines (threat model T-03-05 / T-04-09 / T-05-19 --
no runtime graph modification or user-controlled node selection):

    build_pipeline (Phase 1):
        START -> extract -> analyze -> END
    build_research_pipeline (Phase 3):
        START -> research -> signal -> END
    build_multi_agent_pipeline (Phase 4):
        START -> [fundamental, sentiment, technical] (parallel)
             -> manager -> signal -> END
    build_debate_pipeline (Phase 5):
        START -> [fundamental, sentiment, technical] (parallel)
             -> manager
             -> bull -> bear -> rebuttal -> final_arguments
                 -> debate_synthesis
             -> signal -> END

Each pipeline uses a distinct TypedDict state (PipelineState,
ResearchPipelineState, MultiAgentPipelineState, or DebatePipelineState).
All accept an optional checkpointer to enable PostgreSQL state persistence.

The Phase-5 debate builder is additive (Option B per 05-RESEARCH.md):
``build_multi_agent_pipeline`` is byte-for-byte unchanged so all Phase-4
tests stay green. The debate pipeline reuses the Phase-4 analyst + manager
+ signal nodes; the 5 debate nodes + the sequential edge chain are added
between manager and signal. Critically, the (manager, signal) direct edge
is ABSENT in the debate pipeline -- it would form a diamond with the
debate chain (Pitfall 4).
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ai_hedge_fund.graph.nodes import (
    analyze_node,
    bear_node,
    bull_node,
    debate_synthesis_node,
    extract_node,
    final_arguments_node,
    fundamental_node,
    manager_node,
    multi_agent_signal_node,
    rebuttal_node,
    research_node,
    sentiment_node,
    signal_node,
    technical_node,
)
from ai_hedge_fund.schemas.state import (
    DebatePipelineState,
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


def build_debate_pipeline(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build the Phase-5 adversarial-debate pipeline.

    Topology::

        START -> [fundamental, sentiment, technical] (parallel analysts)
              -> manager
              -> bull -> bear -> rebuttal -> final_arguments
                  -> debate_synthesis
              -> signal
              -> END

    Extends the Phase-4 fan-out / fan-in / manager topology with a strictly
    sequential 5-act debate (SAS-paper protocol). The ``thesis`` field is
    written by ``manager_node`` and OVERWRITTEN by ``debate_synthesis_node``
    with the post-debate ``revised_thesis`` so the downstream signal adapter
    consumes the debated thesis without any changes.

    This is a NEW builder (not a modification of ``build_multi_agent_pipeline``)
    per 05-RESEARCH.md Option B -- preserves all Phase-4 tests and avoids the
    ``(manager, signal)`` diamond (Pitfall 4): the direct edge from manager
    to signal DOES NOT exist in this pipeline.

    Graph topology is compile-time static (threat model T-05-19 -- no runtime
    graph modification). Every node run is bounded by per-agent
    ``UsageLimits``. Budget-exceeded errors short-circuit downstream nodes
    via the ``error`` field; analyst-level failures still propagate inside
    ``analyst_reports`` (same idiom as Phase 4).

    Args:
        checkpointer: Optional LangGraph checkpoint saver for durable state
            persistence. Pass a ``PostgresSaver`` in production.

    Returns:
        Compiled ``StateGraph`` ready for invocation via ``ainvoke``.
    """
    builder = StateGraph(DebatePipelineState)

    # Phase-4 topology (analysts -> manager) -- unchanged.
    builder.add_node("fundamental", fundamental_node)
    builder.add_node("sentiment", sentiment_node)
    builder.add_node("technical", technical_node)
    builder.add_node("manager", manager_node)

    # Phase-5 new debate nodes.
    builder.add_node("bull", bull_node)
    builder.add_node("bear", bear_node)
    builder.add_node("rebuttal", rebuttal_node)
    builder.add_node("final_arguments", final_arguments_node)
    builder.add_node("debate_synthesis", debate_synthesis_node)

    # Reuse the Phase-4 signal adapter -- it reads state['thesis'], which
    # the debate_synthesis_node has overwritten with revised_thesis.
    builder.add_node("signal", multi_agent_signal_node)

    # Fan-out: START -> 3 analysts (same as Phase 4).
    builder.add_edge(START, "fundamental")
    builder.add_edge(START, "sentiment")
    builder.add_edge(START, "technical")

    # Fan-in: analysts -> manager (same as Phase 4).
    builder.add_edge("fundamental", "manager")
    builder.add_edge("sentiment", "manager")
    builder.add_edge("technical", "manager")

    # Sequential 5-act debate: manager -> bull -> bear -> rebuttal ->
    # final_arguments -> debate_synthesis. Critically, there is NO direct
    # (manager, signal) edge -- that would create a diamond (Pitfall 4).
    builder.add_edge("manager", "bull")
    builder.add_edge("bull", "bear")
    builder.add_edge("bear", "rebuttal")
    builder.add_edge("rebuttal", "final_arguments")
    builder.add_edge("final_arguments", "debate_synthesis")

    # Tail: debate_synthesis -> signal -> END.
    builder.add_edge("debate_synthesis", "signal")
    builder.add_edge("signal", END)

    return builder.compile(checkpointer=checkpointer)
