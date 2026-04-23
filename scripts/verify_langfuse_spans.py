"""Phase-8 Wave-0 smoke: verify Langfuse/structlog span coverage for SIG-04.

Runs the composed Phase-7 pipeline (with_memory + with_risk) with all 12 agents
stubbed via TestModel, captures all structlog events via capture_logs(), then
asserts that every agent node emits a 'completion' event with the SIG-04 audit
fields: ticker + input_tokens + output_tokens + total_tokens (plus policy_sha
for the risk_manager + episodic_store events).

Usage:
    uv run --no-sync python scripts/verify_langfuse_spans.py

Exit 0 = coverage adequate, SIG-04 satisfied without production gap-fill.
Exit 1 = one or more nodes missing a required field; print the gap list.

Design notes:
    The smoke runs the pipeline TWICE so both the APPROVED and VETOED paths
    are exercised:

      * APPROVED scenario -- seeded portfolio + Consumer-Staples candidate
        passes all 5 risk checks. Produces ``risk_manager_complete`` (APPROVED
        branch) and ``multi_agent_signal_complete`` (signal node runs).
      * VETOED scenario -- seeded portfolio + Technology candidate exceeds
        the sample policy's sector limit. Produces ``risk_manager_veto`` and
        the signal node is skipped (conditional edge routes to episodic_store
        -> END). This path is exercised so the veto event name is on record
        even though SIG-04 coverage is checked against the APPROVED trace.

    Events from both scenarios are unioned before the coverage check.

Implementation notes:
    * The plan (08-00-PLAN.md Task 3) specified ``signal_complete`` as the
      signal-node event name, but the debate pipeline wires
      ``multi_agent_signal_node`` (which emits ``multi_agent_signal_complete``)
      rather than the Phase-3 ``signal_node``. This script records the real
      event name; see SUMMARY.md "Deviations from Plan" for the Rule-1
      bug-fix note.
    * The plan's sample code omitted ``returns`` from the ``RiskDeps``
      instantiation, but the dataclass requires it -- we load the
      ``returns_golden.csv`` fixture, matching tests/integration/
      test_phase7_e2e.py. Rule 3 (blocking) fix.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import ExitStack
from pathlib import Path

# MUST be set BEFORE importing ai_hedge_fund.agents -- ``analysis_agent`` is
# constructed at module import time and the Anthropic provider raises
# UserError if the key is absent. Mirrors tests/integration/test_phase7_e2e.py.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-phase8-wave0-smoke")

import pandas as pd  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from structlog.testing import capture_logs  # noqa: E402

from ai_hedge_fund.agents.bear import bear_agent  # noqa: E402
from ai_hedge_fund.agents.bull import bull_agent  # noqa: E402
from ai_hedge_fund.agents.debate_synthesis import debate_synthesis_agent  # noqa: E402
from ai_hedge_fund.agents.final_arguments import final_arguments_agent  # noqa: E402
from ai_hedge_fund.agents.fundamental import fundamental_agent  # noqa: E402
from ai_hedge_fund.agents.manager import manager_agent  # noqa: E402
from ai_hedge_fund.agents.rebuttal import rebuttal_agent  # noqa: E402
from ai_hedge_fund.agents.risk_manager import risk_manager_agent  # noqa: E402
from ai_hedge_fund.agents.self_critique import self_critique_agent  # noqa: E402
from ai_hedge_fund.agents.sentiment import sentiment_agent  # noqa: E402
from ai_hedge_fund.agents.signal import signal_agent  # noqa: E402
from ai_hedge_fund.agents.technical import technical_agent  # noqa: E402
from ai_hedge_fund.db.base import Base  # noqa: E402
from ai_hedge_fund.graph.memory_deps import MemoryDeps  # noqa: E402
from ai_hedge_fund.graph.pipeline import build_debate_pipeline  # noqa: E402
from ai_hedge_fund.graph.risk_deps import RiskDeps  # noqa: E402
from ai_hedge_fund.risk.policy import RiskPolicy, load_policy  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RISK_FIXTURES = PROJECT_ROOT / "tests" / "risk" / "fixtures"


# ---------------------------------------------------------------------------
# Per-agent SIG-04 required-field map.
#
# Field semantics (per 08-RESEARCH.md Wave-0 spec + actual node emissions in
# src/ai_hedge_fund/graph/nodes.py):
#   ticker / input_tokens / output_tokens / total_tokens: required for every
#       LLM-backed node so Langfuse can reconstruct per-agent cost.
#   policy_sha: required for risk_manager + episodic_store so the Phase-6 ->
#       Phase-7 audit chain stays verifiable.
# memory_recall / episodic_store skip token fields because those nodes make
# NO LLM calls (deterministic DB read/write).
# ---------------------------------------------------------------------------
REQUIRED_FIELDS_PER_AGENT: dict[str, set[str]] = {
    "fundamental_complete": {"ticker", "input_tokens", "output_tokens", "total_tokens"},
    "sentiment_complete": {"ticker", "input_tokens", "output_tokens", "total_tokens"},
    "technical_complete": {"ticker", "input_tokens", "output_tokens", "total_tokens"},
    "manager_complete": {"ticker", "input_tokens", "output_tokens", "total_tokens"},
    "bull_complete": {"ticker", "input_tokens", "output_tokens", "total_tokens"},
    "bear_complete": {"ticker", "input_tokens", "output_tokens", "total_tokens"},
    "rebuttal_complete": {"ticker", "input_tokens", "output_tokens", "total_tokens"},
    "final_arguments_complete": {"ticker", "input_tokens", "output_tokens", "total_tokens"},
    "debate_synthesis_complete": {"ticker", "input_tokens", "output_tokens", "total_tokens"},
    "risk_manager_complete": {
        "ticker",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "policy_sha",
    },
    # multi_agent_signal_complete (NOT signal_complete) -- the debate pipeline
    # wires multi_agent_signal_node per src/ai_hedge_fund/graph/pipeline.py
    # line 300. Rule-1 fix vs. the plan spec; see SUMMARY.md deviations.
    "multi_agent_signal_complete": {"ticker", "input_tokens", "output_tokens", "total_tokens"},
    # Deterministic nodes -- no LLM call so no token fields.
    "memory_recall_complete": {"ticker"},
    "episodic_store_complete": {"ticker", "policy_sha"},
}


def _load_golden_returns() -> pd.DataFrame:
    """Load the shared Phase-6/7 returns_golden fixture for RiskDeps."""
    return pd.read_csv(
        RISK_FIXTURES / "returns_golden.csv",
        index_col=0,
        parse_dates=True,
    )


def _bear_case_stub() -> dict:
    """BearCase requires >=2 cross-linked claims; mirrors test_phase7_e2e.py."""
    return {
        "ticker": "a",
        "claims": [
            {
                "claim": "a",
                "evidence": "a",
                "source_analyst": "fundamental",
                "addresses_bull_claim": "a",
            },
            {
                "claim": "a",
                "evidence": "a",
                "source_analyst": "fundamental",
                "addresses_bull_claim": "a",
            },
            {
                "claim": "a",
                "evidence": "a",
                "source_analyst": "fundamental",
                "addresses_bull_claim": None,
            },
        ],
        "addressed_bull_claims": ["a", "a"],
        "headline": "a",
    }


def _stubbed_stack() -> ExitStack:
    """All 12 agents under TestModel; mirrors test_phase7_e2e.py::_stubbed_stack."""
    stack = ExitStack()
    stack.enter_context(fundamental_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(sentiment_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(technical_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(manager_agent.override(model=TestModel()))
    stack.enter_context(bull_agent.override(model=TestModel()))
    stack.enter_context(bear_agent.override(model=TestModel(custom_output_args=_bear_case_stub())))
    stack.enter_context(rebuttal_agent.override(model=TestModel()))
    stack.enter_context(final_arguments_agent.override(model=TestModel()))
    stack.enter_context(debate_synthesis_agent.override(model=TestModel()))
    stack.enter_context(
        risk_manager_agent.override(
            model=TestModel(custom_output_args={"rationale": "stubbed risk rationale"})
        )
    )
    stack.enter_context(signal_agent.override(model=TestModel()))
    stack.enter_context(
        self_critique_agent.override(
            model=TestModel(custom_output_args={"rationale": "stubbed critique"})
        )
    )
    return stack


async def run_stubbed_pipeline() -> list[dict]:
    """Run the Phase-7 composed pipeline twice (APPROVED + VETOED); return all events.

    APPROVED run: empty portfolio + Consumer Staples candidate + as_of_date
    inside the returns_golden window (2024-06-03). A clean risk check produces
    ``risk_manager_complete`` and downstream ``multi_agent_signal_complete``.

    VETOED run: also empty portfolio but candidate sector is excluded via a
    tighter temporary policy (we reuse the sample policy + the AAPL ticker
    which will trigger the correlation / drawdown check with a small history
    window); if that does not trigger a veto, the script still has the
    APPROVED events from the first run covering SIG-04. VETOED path is
    exercised to record ``risk_manager_veto`` on stdout (not part of
    REQUIRED_FIELDS_PER_AGENT, but useful for manual inspection).
    """
    events_all: list[dict] = []
    beliefs_dir = Path("/tmp/phase8_wave0_beliefs")
    (beliefs_dir / "tickers").mkdir(parents=True, exist_ok=True)
    (beliefs_dir / "sectors").mkdir(parents=True, exist_ok=True)
    policy_veto = load_policy(RISK_FIXTURES / "risk_policy_sample.yaml")
    # APPROVED policy: wide-open caps so the deterministic checks pass on an
    # empty portfolio + any candidate in the returns_golden window. Keeps the
    # OTC/SPAC exclusions so the VETOED scenario still fires.
    policy_approve = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=50.0,
        max_total_exposure_pct=100.0,
        max_correlation_with_portfolio=0.99,
        correlation_window_days=60,
        max_projected_drawdown_pct=99.0,
        drawdown_window_days=60,
        min_history_days=60,
        excluded_instrument_types=["OTC", "SPAC"],
        excluded_sectors=[],
        size_high_conviction_multiplier=1.0,
        size_medium_conviction_multiplier=0.5,
        size_low_conviction_multiplier=0.25,
    )
    returns = _load_golden_returns()

    # ----- APPROVED scenario -----
    engine_a = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine_a)
    session_a = sessionmaker(bind=engine_a, expire_on_commit=False)()
    risk_deps_a = RiskDeps(db_session=session_a, returns=returns, policy=policy_approve)
    memory_deps_a = MemoryDeps(db_session=session_a, beliefs_path=beliefs_dir)
    graph_a = build_debate_pipeline(
        with_memory=True,
        memory_deps=memory_deps_a,
        with_risk=True,
        risk_deps=risk_deps_a,
    )
    initial_a: dict = {
        "ticker": "PG",
        "as_of_date": "2024-06-03",  # inside returns_golden window
        "candidate_metadata": {"sector": "Consumer Staples", "instrument_type": "equity"},
    }
    try:
        with _stubbed_stack(), capture_logs() as events_a:
            await graph_a.ainvoke(initial_a)
        events_all.extend(list(events_a))
    finally:
        session_a.close()

    # ----- VETOED scenario -----
    engine_b = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine_b)
    session_b = sessionmaker(bind=engine_b, expire_on_commit=False)()
    risk_deps_b = RiskDeps(db_session=session_b, returns=returns, policy=policy_veto)
    memory_deps_b = MemoryDeps(db_session=session_b, beliefs_path=beliefs_dir)
    graph_b = build_debate_pipeline(
        with_memory=True,
        memory_deps=memory_deps_b,
        with_risk=True,
        risk_deps=risk_deps_b,
    )
    initial_b: dict = {
        # OTC instrument_type is on the sample policy's excluded list ->
        # check_exclusions vetoes deterministically.
        "ticker": "AAPL",
        "as_of_date": "2024-06-03",
        "candidate_metadata": {"sector": "Technology", "instrument_type": "OTC"},
    }
    try:
        with _stubbed_stack(), capture_logs() as events_b:
            await graph_b.ainvoke(initial_b)
        events_all.extend(list(events_b))
    finally:
        session_b.close()

    return events_all


def audit_coverage(events: list[dict]) -> dict[str, set[str]]:
    """Return {event_name: missing_fields_set} for each event we care about."""
    gaps: dict[str, set[str]] = {}
    by_event: dict[str, list[dict]] = {}
    for event in events:
        name = event.get("event")
        if name in REQUIRED_FIELDS_PER_AGENT:
            by_event.setdefault(name, []).append(event)

    for name, required in REQUIRED_FIELDS_PER_AGENT.items():
        if name not in by_event:
            gaps[name] = set(required) | {"<EVENT NEVER EMITTED>"}
            continue
        sample = by_event[name][0]
        missing = {f for f in required if f not in sample or sample.get(f) is None}
        if missing:
            gaps[name] = missing
    return gaps


def verify_span_coverage() -> dict[str, set[str]]:
    """Entry point for programmatic callers (tests, CI). Returns gap dict."""
    events = asyncio.run(run_stubbed_pipeline())
    return audit_coverage(events)


def main() -> int:
    events = asyncio.run(run_stubbed_pipeline())
    print(f"Captured {len(events)} structlog events during the Phase-7 composed pipeline run.\n")
    gaps = audit_coverage(events)
    if not gaps:
        print("SIG-04 audit coverage: ALL REQUIRED FIELDS PRESENT.")
        print("A7 assumption discharged -- existing Phase 1-7 instrumentation is sufficient.")
        return 0
    print("SIG-04 audit coverage GAPS detected (A7 assumption partially invalid):")
    for name, missing in gaps.items():
        print(f"  - {name}: missing {sorted(missing)}")
    print("\nPlan 08-05 (integration) must gap-fill these before phase gate.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
