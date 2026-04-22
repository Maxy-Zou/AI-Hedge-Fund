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

from ai_hedge_fund.graph.memory_deps import MemoryDeps
from ai_hedge_fund.graph.nodes import (
    analyze_node,
    bear_node,
    bull_node,
    debate_synthesis_node,
    episodic_store_node,
    extract_node,
    final_arguments_node,
    fundamental_node,
    manager_node,
    memory_recall_node,
    multi_agent_signal_node,
    rebuttal_node,
    research_node,
    risk_manager_node,
    route_after_risk,
    sentiment_node,
    signal_node,
    technical_node,
)
from ai_hedge_fund.graph.risk_deps import RiskDeps
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
    *,
    with_risk: bool = False,
    risk_deps: RiskDeps | None = None,
    with_memory: bool = False,
    memory_deps: MemoryDeps | None = None,
) -> CompiledStateGraph:
    """Build the Phase-5 adversarial-debate pipeline (+ Phase-6 risk gate,
    + Phase-7 memory substrate).

    Topology when ``with_risk=True`` only (Phase-6)::

        START -> [fundamental, sentiment, technical] (parallel analysts)
              -> manager
              -> bull -> bear -> rebuttal -> final_arguments
                  -> debate_synthesis
              -> risk_manager -[conditional]-> {signal -> END | END}

    Topology when ``with_risk=False`` (Phase-5 backcompat regression)::

        ...
              -> debate_synthesis -> signal -> END

    Topology when ``with_memory=True`` (Phase-7, no risk)::

        START -> memory_recall -> [3 analysts] -> manager
              -> bull -> bear -> rebuttal -> final_arguments
                  -> debate_synthesis -> signal -> episodic_store -> END

    Topology when both ``with_memory=True`` and ``with_risk=True``
    (Phase-7 composed with Phase-6)::

        START -> memory_recall -> [3 analysts] -> manager
              -> bull -> bear -> rebuttal -> final_arguments
                  -> debate_synthesis
              -> risk_manager -[conditional]->
                  {signal -> episodic_store -> END | episodic_store -> END}

    BOTH the APPROVED and VETOED paths flow into ``episodic_store``
    before END -- vetoes are the richest learning signal
    (07-RESEARCH.md Open Question 1 recommendation).

    Phase-5 extended the Phase-4 fan-out / fan-in / manager topology with a
    strictly sequential 5-act debate. Phase-6 adds a single ``risk_manager``
    node between ``debate_synthesis`` and ``signal`` with a conditional
    edge: approved signals proceed to ``signal``; vetoed signals end the
    graph without invoking the signal agent. The ``risk_assessment`` field
    on :class:`DebatePipelineState` carries the decision downstream so
    Phase-8 consumers can surface the veto reason before any trade.

    The conditional router (:func:`route_after_risk`) fails CLOSED:
    missing or ``None`` ``risk_assessment`` routes to ``__end__``, not to
    ``signal`` (Pitfall 7). The ``with_risk=False`` path is preserved
    verbatim so the Phase-5 integration tests in
    ``tests/integration/test_debate_pipeline.py`` stay green.

    Graph topology is compile-time static (threat model T-05-19 / T-06-08 /
    T-07-22 -- no runtime modification). Every node run is bounded by
    per-agent ``UsageLimits``. Analyst-level failures still propagate
    inside ``analyst_reports`` (same idiom as Phase 4).

    Args:
        checkpointer: Optional LangGraph checkpoint saver for durable state
            persistence. Pass a ``PostgresSaver`` in production.
        with_risk: When True, wires the Phase-6 risk gate. When False
            (default), builds the Phase-5 topology (for regression
            testing).
        risk_deps: Bound :class:`RiskDeps` consumed by ``risk_manager_node``.
            Required when ``with_risk=True``; must be ``None`` otherwise.
        with_memory: When True, wires the Phase-7 memory substrate
            (``memory_recall`` before the analysts, ``episodic_store``
            after signal/veto). When False (default), memory nodes are
            absent from the graph (backcompat).
        memory_deps: Bound :class:`MemoryDeps` consumed by the two memory
            nodes. Required when ``with_memory=True``; must be ``None``
            otherwise.

    Returns:
        Compiled ``StateGraph`` ready for invocation via ``ainvoke``.

    Raises:
        ValueError: When ``with_risk=True`` but ``risk_deps`` is ``None``,
            OR when ``with_memory=True`` but ``memory_deps`` is ``None``
            -- the corresponding node(s) cannot run without dependencies.
    """
    if with_risk and risk_deps is None:
        raise ValueError(
            "build_debate_pipeline(with_risk=True) requires risk_deps -- "
            "supply a RiskDeps instance with db_session and returns."
        )
    if with_memory and memory_deps is None:
        raise ValueError(
            "build_debate_pipeline(with_memory=True) requires memory_deps -- "
            "supply a MemoryDeps instance with db_session and beliefs_path."
        )

    builder = StateGraph(DebatePipelineState)

    # Phase-4 topology (analysts -> manager) -- unchanged.
    builder.add_node("fundamental", fundamental_node)
    builder.add_node("sentiment", sentiment_node)
    builder.add_node("technical", technical_node)
    builder.add_node("manager", manager_node)

    # Phase-5 debate nodes.
    builder.add_node("bull", bull_node)
    builder.add_node("bear", bear_node)
    builder.add_node("rebuttal", rebuttal_node)
    builder.add_node("final_arguments", final_arguments_node)
    builder.add_node("debate_synthesis", debate_synthesis_node)

    # Reuse the Phase-4 signal adapter -- it reads state['thesis'], which
    # the debate_synthesis_node has overwritten with revised_thesis.
    builder.add_node("signal", multi_agent_signal_node)

    if with_risk:
        assert risk_deps is not None  # for the type checker; enforced above

        async def _risk_manager_bound(state: DebatePipelineState) -> dict:
            return await risk_manager_node(state, risk_deps)

        builder.add_node("risk_manager", _risk_manager_bound)

    if with_memory:
        assert memory_deps is not None  # for the type checker; enforced above

        async def _memory_recall_bound(state: DebatePipelineState) -> dict:
            return await memory_recall_node(state, memory_deps)

        async def _episodic_store_bound(state: DebatePipelineState) -> dict:
            return await episodic_store_node(state, memory_deps)

        builder.add_node("memory_recall", _memory_recall_bound)
        builder.add_node("episodic_store", _episodic_store_bound)

    # Fan-out: START -> memory_recall (if enabled) -> 3 analysts, else
    # START -> 3 analysts directly (Phase-4/5 topology preserved byte-for-byte
    # when with_memory=False).
    if with_memory:
        builder.add_edge(START, "memory_recall")
        builder.add_edge("memory_recall", "fundamental")
        builder.add_edge("memory_recall", "sentiment")
        builder.add_edge("memory_recall", "technical")
    else:
        builder.add_edge(START, "fundamental")
        builder.add_edge(START, "sentiment")
        builder.add_edge(START, "technical")

    # Fan-in: analysts -> manager (same as Phase 4).
    builder.add_edge("fundamental", "manager")
    builder.add_edge("sentiment", "manager")
    builder.add_edge("technical", "manager")

    # Sequential 5-act debate: manager -> bull -> bear -> rebuttal ->
    # final_arguments -> debate_synthesis. No direct (manager, signal)
    # edge -- that would create a diamond (Phase-5 Pitfall 4).
    builder.add_edge("manager", "bull")
    builder.add_edge("bull", "bear")
    builder.add_edge("bear", "rebuttal")
    builder.add_edge("rebuttal", "final_arguments")
    builder.add_edge("final_arguments", "debate_synthesis")

    if with_risk:
        # Phase-6: debate_synthesis -> risk_manager -[conditional]-> {signal, END}.
        # No direct (debate_synthesis, signal) edge when risk is active -- the
        # risk node is the single gatekeeper.
        builder.add_edge("debate_synthesis", "risk_manager")
        if with_memory:
            # Memory + risk: BOTH APPROVED and VETOED paths flow into
            # episodic_store before END. Vetoed decisions are persisted
            # (07-RESEARCH.md Open Question 1 -- vetoes are the richest
            # learning signal).
            builder.add_conditional_edges(
                "risk_manager",
                route_after_risk,
                {"signal": "signal", "__end__": "episodic_store"},
            )
            builder.add_edge("signal", "episodic_store")
            builder.add_edge("episodic_store", END)
        else:
            # Risk only (Phase-6 topology, unchanged).
            builder.add_conditional_edges(
                "risk_manager",
                route_after_risk,
                {"signal": "signal", "__end__": END},
            )
            builder.add_edge("signal", END)
    else:
        # No risk gate.
        builder.add_edge("debate_synthesis", "signal")
        if with_memory:
            # Memory only: signal -> episodic_store -> END.
            builder.add_edge("signal", "episodic_store")
            builder.add_edge("episodic_store", END)
        else:
            # Phase-5 backcompat: signal -> END (byte-for-byte unchanged).
            builder.add_edge("signal", END)

    return builder.compile(checkpointer=checkpointer)
