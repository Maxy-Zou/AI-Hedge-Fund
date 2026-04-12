"""Integration tests for the Phase-3 research pipeline.

Three test categories:

A. **Pipeline compilation tests** (always run, no API key, no DB).
   Verify that ``build_research_pipeline`` returns a ``CompiledStateGraph``
   with and without a ``MemorySaver`` checkpointer.

B. **TestModel-based tests** (always run, no real LLM).
   Use PydanticAI's ``TestModel`` to override the research and signal
   agents' underlying model with a canned, schema-valid response. These
   tests validate pipeline flow and agent wiring without network calls.

C. **Real LLM integration tests** (skip without real API key + EDGAR
   identity). These are guarded by ``requires_real_llm`` and, where the
   research agent calls SEC EDGAR, by ``requires_edgar_identity``. The
   research pipeline exercises all 6 data tools and multi-step LLM
   reasoning, so tests may take 30-90 seconds per invocation.

Rationale for ``call_tools=[]``:
    ``TestModel`` with the default ``call_tools='all'`` will invoke every
    registered tool on the agent. The research agent's tools hit SEC
    EDGAR and yfinance -- network calls with side effects we do not want
    in the unit test path. Setting ``call_tools=[]`` disables tool
    invocation and has TestModel produce the final output directly.

Expected test timings:
    - Pipeline compilation tests: sub-second.
    - TestModel tests: <1 second.
    - Real LLM tests: 30-90 seconds per test (no pytest-timeout available
      in this project; rely on manual supervision and the Anthropic SDK's
      own timeout).
"""

from __future__ import annotations

import os
from datetime import date

# Set dummy API key before importing agents (PydanticAI validates at construction).
# Mirrors the pattern used in tests/unit/test_research_agent.py and
# tests/integration/test_graph.py.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pytest  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.graph.state import CompiledStateGraph  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402

from ai_hedge_fund.agents.research import ResearchDeps, research_agent  # noqa: E402
from ai_hedge_fund.agents.signal import signal_agent  # noqa: E402
from ai_hedge_fund.graph.pipeline import build_research_pipeline  # noqa: E402
from ai_hedge_fund.schemas.agents import SignalOutput, ThesisOutput  # noqa: E402
from ai_hedge_fund.schemas.state import ResearchPipelineState  # noqa: E402, F401

# A dummy API key used for agent construction in tests -- not valid for LLM calls.
_DUMMY_KEY_PREFIX = "test-key"


def _has_real_api_key() -> bool:
    """Check if ANTHROPIC_API_KEY is set to a real key (not a dummy test key)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(key) and not key.startswith(_DUMMY_KEY_PREFIX)


def _has_edgar_identity() -> bool:
    """Check if EDGAR_IDENTITY is set (required for SEC EDGAR API access)."""
    identity = os.environ.get("EDGAR_IDENTITY", "")
    return bool(identity) and "@" in identity


# ---------------------------------------------------------------------------
# A. Pipeline compilation tests (always run)
# ---------------------------------------------------------------------------


def test_research_pipeline_compiles() -> None:
    """build_research_pipeline() returns a CompiledStateGraph without checkpointer."""
    graph = build_research_pipeline()
    assert graph is not None
    assert isinstance(graph, CompiledStateGraph)
    assert hasattr(graph, "ainvoke")


def test_research_pipeline_with_checkpointer() -> None:
    """build_research_pipeline() compiles with a MemorySaver checkpointer."""
    checkpointer = MemorySaver()
    graph = build_research_pipeline(checkpointer=checkpointer)
    assert graph is not None
    assert isinstance(graph, CompiledStateGraph)
    assert hasattr(graph, "ainvoke")


# ---------------------------------------------------------------------------
# B. TestModel-based tests (always run, no real LLM, no network)
# ---------------------------------------------------------------------------


async def test_research_agent_with_test_model() -> None:
    """Overriding research_agent with TestModel produces a valid ThesisOutput.

    Uses ``call_tools=[]`` so TestModel does not invoke the real data
    tool wrappers (which hit SEC EDGAR / yfinance). TestModel auto-fills
    fields to satisfy the ThesisOutput schema constraints (min_length=3
    bull/bear points, min_length=2 risk factors, confidence 0-100).
    """
    with research_agent.override(model=TestModel(call_tools=[])):
        deps = ResearchDeps(ticker="AAPL", as_of_date=date(2024, 1, 2))
        result = await research_agent.run(
            "Produce an investment thesis for AAPL",
            deps=deps,
        )

    assert isinstance(result.output, ThesisOutput)
    assert len(result.output.bull_case) >= 3
    assert len(result.output.bear_case) >= 3
    assert len(result.output.risk_factors) >= 2
    assert 0 <= result.output.confidence <= 100


async def test_signal_agent_with_test_model() -> None:
    """Overriding signal_agent with TestModel produces a valid SignalOutput.

    The signal agent has no tools, so ``call_tools`` default is irrelevant.
    TestModel fills direction/conviction from the Literal choices and
    position_size_pct within the 0-100 ge/le bounds.
    """
    thesis_prompt = (
        "Generate a trade signal from this thesis:\n"
        '{"ticker": "AAPL", "bull_case": [{"claim": "strong", "evidence": "x", '
        '"source_tool": "get_financials"}], "confidence": 70, '
        '"risk_factors": ["macro"]}'
    )
    with signal_agent.override(model=TestModel()):
        result = await signal_agent.run(thesis_prompt)

    assert isinstance(result.output, SignalOutput)
    assert result.output.direction in {"long", "short", "neutral"}
    assert result.output.conviction in {"low", "medium", "high"}
    assert 0.0 <= result.output.position_size_pct <= 100.0
    assert isinstance(result.output.time_horizon, str) and len(result.output.time_horizon) > 0


# ---------------------------------------------------------------------------
# C. Real LLM integration tests (require real API keys; skip otherwise)
# ---------------------------------------------------------------------------

requires_real_llm = pytest.mark.skipif(
    not _has_real_api_key(),
    reason="Real ANTHROPIC_API_KEY not set -- skipping real-LLM integration test",
)

requires_edgar_identity = pytest.mark.skipif(
    not _has_edgar_identity(),
    reason="EDGAR_IDENTITY not set -- skipping SEC EDGAR-backed integration test",
)


@requires_real_llm
@requires_edgar_identity
async def test_full_pipeline_real_llm() -> None:
    """Full research agent run against a real ticker produces a valid ThesisOutput.

    Runs the research agent directly (not via pipeline) against AAPL as of
    2024-01-02. The agent must:
      - Produce a ThesisOutput with >= 3 bull points, >= 3 bear points,
        >= 2 risk factors.
      - Confidence must be in the 0-100 range.
      - Every bull/bear point must cite a source_tool.

    Expected duration: ~30-60 seconds depending on tool call count.
    """
    deps = ResearchDeps(ticker="AAPL", as_of_date=date(2024, 1, 2))
    result = await research_agent.run(
        "Produce a comprehensive investment thesis for AAPL",
        deps=deps,
    )

    thesis = result.output
    assert isinstance(thesis, ThesisOutput)
    assert thesis.ticker.upper() == "AAPL" or "AAPL" in thesis.ticker.upper()
    assert len(thesis.bull_case) >= 3, (
        f"Bull case needs >= 3 points, got {len(thesis.bull_case)}"
    )
    assert len(thesis.bear_case) >= 3, (
        f"Bear case needs >= 3 points, got {len(thesis.bear_case)}"
    )
    assert len(thesis.risk_factors) >= 2, (
        f"Risk factors need >= 2, got {len(thesis.risk_factors)}"
    )
    assert 0 <= thesis.confidence <= 100, f"Confidence out of range: {thesis.confidence}"
    for point in thesis.bull_case:
        assert point.source_tool, "Bull point missing source_tool"
    for point in thesis.bear_case:
        assert point.source_tool, "Bear point missing source_tool"


@requires_real_llm
@requires_edgar_identity
async def test_temporal_correctness_real_llm() -> None:
    """Same ticker + different as_of_dates produce materially different theses.

    This is the phase-level temporal correctness criterion (ROADMAP Phase 3
    success criterion 4). If the agent's ``as_of_date`` restriction works,
    analyzing AAPL as of 2024-01-02 should yield a thesis materially
    different from one generated as of 2025-01-02 (different prices,
    different filings, different macro context).

    "Materially different" is evaluated across three weak signals, any of
    which passing the assertion:
      - Different confidence scores.
      - Different lengths of bull/bear/risk lists.
      - Different first bull claim text.
    This uses OR rather than AND because any single one is strong enough
    evidence that temporal controls are working; requiring all three
    would make the test flaky against LLM non-determinism.

    Expected duration: 60-120 seconds (two research runs).
    """
    deps_2024 = ResearchDeps(ticker="AAPL", as_of_date=date(2024, 1, 2))
    deps_2025 = ResearchDeps(ticker="AAPL", as_of_date=date(2025, 1, 2))

    result_2024 = await research_agent.run(
        "Produce a comprehensive investment thesis for AAPL",
        deps=deps_2024,
    )
    result_2025 = await research_agent.run(
        "Produce a comprehensive investment thesis for AAPL",
        deps=deps_2025,
    )

    t24 = result_2024.output
    t25 = result_2025.output
    # Weak signal 1: confidence differs.
    confidence_differs = t24.confidence != t25.confidence
    # Weak signal 2: list lengths differ (bull/bear/risks).
    lengths_differ = (
        len(t24.bull_case) != len(t25.bull_case)
        or len(t24.bear_case) != len(t25.bear_case)
        or len(t24.risk_factors) != len(t25.risk_factors)
    )
    # Weak signal 3: first bull claim differs.
    first_claim_differs = (
        t24.bull_case[0].claim.strip() != t25.bull_case[0].claim.strip()
    )
    assert confidence_differs or lengths_differ or first_claim_differs, (
        "Theses for same ticker with different as_of_dates look identical -- "
        "temporal controls may be leaking. 2024 confidence="
        f"{t24.confidence}, 2025 confidence={t25.confidence}; "
        f"2024 bull[0]={t24.bull_case[0].claim[:60]!r}; "
        f"2025 bull[0]={t25.bull_case[0].claim[:60]!r}"
    )


@requires_real_llm
async def test_signal_from_thesis_real_llm() -> None:
    """signal_agent produces a valid SignalOutput from a realistic thesis.

    Constructs a hand-crafted, schema-valid ThesisOutput dict and feeds it
    to the signal agent. The signal agent has no tools and requires no
    EDGAR identity (thesis arrives via prompt), so only ANTHROPIC_API_KEY
    is required.

    Expected duration: 5-15 seconds.
    """
    thesis = {
        "ticker": "AAPL",
        "bull_case": [
            {
                "claim": "Services revenue growth of 12% YoY",
                "evidence": "Services segment $85B up from $78B",
                "source_tool": "get_financials",
            },
            {
                "claim": "Net margin expansion to 25%",
                "evidence": "Operating leverage on services mix",
                "source_tool": "get_financials",
            },
            {
                "claim": "Insider purchases in prior quarter",
                "evidence": "Cluster of 3 executive buys at $180",
                "source_tool": "get_insider_activity",
            },
        ],
        "bear_case": [
            {
                "claim": "China demand deterioration",
                "evidence": "Greater China revenue down 8% YoY",
                "source_tool": "get_financials",
            },
            {
                "claim": "Hardware cycle maturity",
                "evidence": "iPhone replacement cycles lengthening",
                "source_tool": "fetch_filings",
            },
            {
                "claim": "Rising rate environment pressures multiples",
                "evidence": "10Y yield at 4.5% per FRED",
                "source_tool": "get_macro_environment",
            },
        ],
        "confidence": 62,
        "risk_factors": [
            "Regulatory action on App Store economics",
            "Accelerating competition in AI-capable devices",
        ],
    }
    prompt = f"Generate a trade signal for AAPL based on this thesis:\n{thesis}"
    result = await signal_agent.run(prompt)

    signal = result.output
    assert isinstance(signal, SignalOutput)
    assert signal.direction in {"long", "short", "neutral"}
    assert signal.conviction in {"low", "medium", "high"}
    assert isinstance(signal.time_horizon, str) and len(signal.time_horizon) > 0
    assert 0.0 <= signal.position_size_pct <= 100.0
    assert isinstance(signal.thesis_summary, str) and len(signal.thesis_summary) > 0
