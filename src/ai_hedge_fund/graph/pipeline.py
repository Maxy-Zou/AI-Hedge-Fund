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
    human_review_node,
    manager_node,
    memory_recall_node,
    multi_agent_signal_node,
    output_node,
    rebuttal_node,
    research_node,
    review_store_node,
    risk_manager_node,
    route_after_risk,
    route_before_review,
    sentiment_node,
    signal_node,
    technical_node,
)
from ai_hedge_fund.graph.review_deps import ReviewDeps
from ai_hedge_fund.graph.risk_deps import RiskDeps
from ai_hedge_fund.review.policy import load_review_policy
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
            persistence. Pass an AsyncPostgresSaver (from
            ``create_async_checkpointer``) for durable execution.

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
            persistence. Pass an AsyncPostgresSaver (from
            ``create_async_checkpointer``) for durable execution.

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
            state persistence. Pass an ``AsyncPostgresSaver`` (from
            ``create_async_checkpointer``) in production.

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
    with_output: bool = False,
    with_review: bool = False,
    review_deps: ReviewDeps | None = None,
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
            persistence. Pass an ``AsyncPostgresSaver`` (from
            ``create_async_checkpointer``) in production.
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
        with_output: When True (Phase 8 SIG-01), inserts ``output_node``
            after ``episodic_store`` to assemble the
            :class:`ai_hedge_fund.schemas.signal_output.FinalSignalOutput`.
            Requires ``with_memory=True`` (output_node needs
            ``episodic_stored_id`` for ``thesis_link``) and ``review_deps``
            (for the ``review_policy_sha`` stamp). Does NOT imply
            ``with_review``.
        with_review: When True (Phase 8 SIG-03), wires the
            ``human_review_node`` behind a conditional edge
            (:func:`route_before_review`). Signals with conviction >=
            threshold pause the graph via :func:`langgraph.types.interrupt`;
            below-threshold signals route directly to ``review_store``.
            Requires ``with_output=True``, ``review_deps``, and a
            ``checkpointer`` (the interrupt primitive persists state via
            the checkpointer -- Pitfall I).

            Note: callers using ``with_review=True`` MUST seed initial
            state with ``_review_threshold`` (read from
            ``review_deps.policy.conviction_threshold``). The
            ``run_analysis`` CLI (Plan 08-04) handles this; tests inject
            it in the initial state dict.
        review_deps: Bound :class:`ReviewDeps` (db_session + policy XOR
            policy_path). Required when ``with_output=True``; reused by
            both ``output_node`` (for the SHA stamp) and
            ``review_store_node`` (for the audit row append).

    Returns:
        Compiled ``StateGraph`` ready for invocation via ``ainvoke``.

    Raises:
        ValueError: When any of these invalid combinations are passed:
            * ``with_risk=True`` but ``risk_deps`` is ``None``;
            * ``with_memory=True`` but ``memory_deps`` is ``None``;
            * ``with_output=True`` but ``with_memory=False`` (Phase-8
              T-08-23 -- output_node needs ``episodic_stored_id``);
            * ``with_output=True`` but ``review_deps`` is ``None``;
            * ``with_review=True`` but ``with_output=False`` (the gate
              reads from ``final_signal``);
            * ``with_review=True`` but ``checkpointer`` is ``None``
              (Pitfall I -- Phase-8 T-08-21).
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
    # --- Phase-8 guards ---
    if with_output and not with_memory:
        raise ValueError(
            "build_debate_pipeline(with_output=True) requires with_memory=True "
            "-- output_node needs episodic_stored_id from episodic_store_node."
        )
    if with_output and review_deps is None:
        raise ValueError(
            "build_debate_pipeline(with_output=True) requires review_deps -- "
            "supply a ReviewDeps instance with db_session and policy "
            "(or policy_path)."
        )
    if with_review and not with_output:
        raise ValueError(
            "build_debate_pipeline(with_review=True) requires with_output=True "
            "-- the review gate reads from final_signal."
        )
    if with_review and checkpointer is None:
        raise ValueError(
            "build_debate_pipeline(with_review=True) requires a checkpointer "
            "-- langgraph.types.interrupt() persists state via the checkpointer."
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

    if with_output:
        # Resolve the review policy once at build time so each node call
        # avoids re-loading the YAML. Pipeline-builder owns the
        # XOR-policy/policy_path resolution; the bound closures below
        # see a normalised ReviewDeps with policy populated.
        assert review_deps is not None  # for the type checker; enforced above
        if review_deps.policy is not None:
            _resolved_review_deps = review_deps
        else:
            assert review_deps.policy_path is not None
            _loaded_policy = load_review_policy(review_deps.policy_path)
            _resolved_review_deps = ReviewDeps(
                db_session=review_deps.db_session,
                policy=_loaded_policy,
            )

        async def _output_bound(state: DebatePipelineState) -> dict:
            return await output_node(state, _resolved_review_deps)

        async def _review_store_bound(state: DebatePipelineState) -> dict:
            return await review_store_node(state, _resolved_review_deps)

        builder.add_node("output", _output_bound)
        builder.add_node("review_store", _review_store_bound)

    if with_review:
        # human_review_node has no deps -- the interrupt primitive is
        # owned by langgraph itself and the resumed payload is validated
        # in-node via ReviewDecision.model_validate.
        builder.add_node("human_review", human_review_node)

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
            # When with_output is enabled, episodic_store flows into output_node
            # (Phase-8); otherwise it terminates the graph (Phase-7 backcompat).
            if not with_output:
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
            # When with_output is enabled, episodic_store flows into output_node
            # (Phase-8); otherwise it terminates the graph (Phase-7 backcompat).
            if not with_output:
                builder.add_edge("episodic_store", END)
        else:
            # Phase-5 backcompat: signal -> END (byte-for-byte unchanged).
            builder.add_edge("signal", END)

    if with_output:
        # Phase-8 tail: episodic_store -> output -> (human_review|review_store) -> END.
        # Guarded by the `with_output and not with_memory` ValueError above,
        # so episodic_store is guaranteed registered when this branch fires.
        builder.add_edge("episodic_store", "output")

        if with_review:
            # Conditional: above-threshold conviction -> human_review;
            # below-threshold -> straight to review_store (NOT_REQUIRED row).
            builder.add_conditional_edges(
                "output",
                route_before_review,
                {"human_review": "human_review", "review_store": "review_store"},
            )
            builder.add_edge("human_review", "review_store")
        else:
            # No review gate -- output flows directly into review_store
            # (writes a NOT_REQUIRED audit row).
            builder.add_edge("output", "review_store")

        builder.add_edge("review_store", END)

    return builder.compile(checkpointer=checkpointer)
