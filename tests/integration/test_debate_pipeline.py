"""Integration tests for the Phase-5 debate pipeline (all 10 agents, TestModel).

Three test categories:

A. **Pipeline compilation** (always run, no API key, no DB) -- verifies
   ``build_debate_pipeline`` returns a ``CompiledStateGraph`` with and
   without a checkpointer.

B. **TestModel-based end-to-end flow** (always run, no real LLM, no
   network) -- overrides every agent (3 analysts + manager + 5 debate +
   signal = 10 total) with PydanticAI's ``TestModel``, invokes the
   compiled pipeline via ``ainvoke``, and verifies:

     - All 5 debate acts populated with non-None structured output.
     - ``debate_synthesis['quality_score']`` equals the deterministic
       weighted mean ``round(0.4*e + 0.3*l + 0.3*r)`` -- DEBATE-04 / T-05-17
       enforcement (the LLM's quality_score is overwritten by the pipeline).
     - ``state['thesis'] == debate_synthesis['revised_thesis']`` (thesis
       was overwritten by ``debate_synthesis_node`` so the signal node
       consumes the post-debate version unchanged -- RESEARCH.md Q3).
     - ``state['signal']`` is populated (debate-signal flow works end-to-end).

   ``call_tools=[]`` is required on the three analyst agents because
   their tools hit SEC EDGAR / yfinance / Finnhub and would cause real
   network side effects during unit testing. The 7 zero-tool agents
   (manager + 5 debate + signal) use the default ``TestModel()``.

C. **Phase-4 no-regression** -- confirms ``build_multi_agent_pipeline``
   still compiles (the unchanged Phase-4 integration test runs
   separately for deeper Phase-4 checks).

Expected timings:
    - Compilation tests: sub-second.
    - TestModel flow test: <2 seconds.

No real-LLM tests in this file -- the 10-agent debate pipeline would
cost several dollars per run, so real-LLM evaluation is gated behind
phase-level UAT scripts per 05-VALIDATION.md.
"""

from __future__ import annotations

import asyncio
import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.graph.state import CompiledStateGraph  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402

from ai_hedge_fund.agents.bear import bear_agent  # noqa: E402
from ai_hedge_fund.agents.bull import bull_agent  # noqa: E402
from ai_hedge_fund.agents.debate_synthesis import (  # noqa: E402
    debate_synthesis_agent,
)
from ai_hedge_fund.agents.final_arguments import final_arguments_agent  # noqa: E402
from ai_hedge_fund.agents.fundamental import fundamental_agent  # noqa: E402
from ai_hedge_fund.agents.manager import manager_agent  # noqa: E402
from ai_hedge_fund.agents.rebuttal import rebuttal_agent  # noqa: E402
from ai_hedge_fund.agents.sentiment import sentiment_agent  # noqa: E402
from ai_hedge_fund.agents.signal import signal_agent  # noqa: E402
from ai_hedge_fund.agents.technical import technical_agent  # noqa: E402
from ai_hedge_fund.graph.pipeline import (  # noqa: E402
    build_debate_pipeline,
    build_multi_agent_pipeline,
)


# ---------------------------------------------------------------------------
# A. Compilation
# ---------------------------------------------------------------------------


class TestDebatePipelineCompilation:
    def test_compiles_without_checkpointer(self) -> None:
        graph = build_debate_pipeline()
        assert isinstance(graph, CompiledStateGraph)

    def test_compiles_with_memory_checkpointer(self) -> None:
        graph = build_debate_pipeline(checkpointer=MemorySaver())
        assert isinstance(graph, CompiledStateGraph)


# ---------------------------------------------------------------------------
# B. End-to-end with TestModel on all 10 agents
# ---------------------------------------------------------------------------


class TestDebatePipelineEndToEnd:
    def test_full_debate_pipeline_with_test_model(self) -> None:
        """Invoke the compiled graph end-to-end with TestModel on all 10 agents.

        Verifies DEBATE-03 (all 5 acts execute in order with structured
        outputs) AND DEBATE-04 (quality_score is the deterministic weighted
        mean, not the LLM value).
        """
        graph = build_debate_pipeline()
        initial_state = {"ticker": "AAPL", "as_of_date": "2024-01-02"}

        async def _invoke() -> dict:
            with (
                fundamental_agent.override(model=TestModel(call_tools=[])),
                sentiment_agent.override(model=TestModel(call_tools=[])),
                technical_agent.override(model=TestModel(call_tools=[])),
                manager_agent.override(model=TestModel()),
                bull_agent.override(model=TestModel()),
                bear_agent.override(model=TestModel()),
                rebuttal_agent.override(model=TestModel()),
                final_arguments_agent.override(model=TestModel()),
                debate_synthesis_agent.override(model=TestModel()),
                signal_agent.override(model=TestModel()),
            ):
                return await graph.ainvoke(initial_state)

        final_state = asyncio.run(_invoke())

        # No pipeline-level error.
        assert final_state.get("error") is None, (
            f"Pipeline errored: {final_state.get('error')}"
        )

        # All 3 analyst reports via the operator.add reducer.
        reports = final_state.get("analyst_reports", [])
        assert len(reports) == 3, f"Expected 3 analyst reports, got {len(reports)}"

        # All 5 debate acts produced structured output.
        assert final_state.get("bull_case") is not None
        assert final_state["bull_case"]["claims"]  # min_length=3 by schema
        assert len(final_state["bull_case"]["claims"]) >= 3

        assert final_state.get("bear_case") is not None
        assert final_state["bear_case"]["addressed_bull_claims"]
        assert len(final_state["bear_case"]["addressed_bull_claims"]) >= 2

        assert final_state.get("rebuttal") is not None
        assert len(final_state["rebuttal"]["bull_rebuttals"]) >= 2
        assert len(final_state["rebuttal"]["bear_rebuttals"]) >= 2

        assert final_state.get("final_arguments") is not None

        # Debate synthesis populated.
        synth = final_state.get("debate_synthesis")
        assert synth is not None
        assert 0 <= synth["quality_score"] <= 100

        # DEBATE-04 enforcement: quality_score is the deterministic weighted
        # mean, NOT whatever the LLM returned. compute_quality_score uses
        # weights 0.4 / 0.3 / 0.3.
        expected = round(
            0.4 * synth["evidence_strength"]
            + 0.3 * synth["logical_consistency"]
            + 0.3 * synth["risk_coverage"]
        )
        assert synth["quality_score"] == expected, (
            f"quality_score {synth['quality_score']} != expected {expected} "
            f"from sub-scores (evidence={synth['evidence_strength']}, "
            f"logic={synth['logical_consistency']}, "
            f"risk={synth['risk_coverage']}). "
            "debate_synthesis_node must overwrite the LLM's value with "
            "compute_quality_score()."
        )

        # Q3 enforcement: thesis was OVERWRITTEN with revised_thesis so the
        # signal node consumed the debated version.
        assert final_state["thesis"] == synth["revised_thesis"], (
            "state['thesis'] must equal debate_synthesis['revised_thesis'] "
            "-- debate_synthesis_node must overwrite state['thesis'] so the "
            "downstream signal_node consumes the post-debate version."
        )

        # Signal was produced from the revised thesis.
        assert final_state.get("signal") is not None


# ---------------------------------------------------------------------------
# C. Phase-4 no-regression
# ---------------------------------------------------------------------------


class TestPhase4PipelineNoRegression:
    """Option B promise: Phase-4 pipeline is unchanged and still compiles."""

    def test_phase4_pipeline_compiles(self) -> None:
        graph = build_multi_agent_pipeline()
        assert isinstance(graph, CompiledStateGraph)
