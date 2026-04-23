"""Phase 8 end-to-end integration tests (phase gate).

Shipped as part of Plan 08-05 -- zero new production code. Tests compose
the full Phase 5+6+7+8 pipeline under TestModel stubs. Eight scenarios
prove SIG-01..04 end-to-end:

    1. Above-threshold run fires LangGraph __interrupt__
    2. Below-threshold run bypasses review (review_status='NOT_REQUIRED')
    3. APPROVED resume completes the pipeline; review row persisted
    4. REJECTED resume persists row with status='REJECTED'; analysis row
       is byte-identical (append-only invariant)
    5. VETOED path NEVER reaches review (no interrupt, no review row)
    6. NOT_REQUIRED path still writes a record_type='review' row for
       audit uniformity
    7. Portfolio view freshness: after a successful run, query_portfolio_view
       immediately surfaces the ticker (no cache)
    8. Phase-5 backcompat: no-kwargs pipeline still compiles to Phase-5 topology

All 12 agents (11 debate/risk + self_critique) stubbed via TestModel. Zero
real LLM calls. RiskDeps consumes the ``returns_golden.csv`` fixture (Phase-6
pattern); as_of_date lives inside that window (2024-06-03) so the
deterministic risk checks pass on an empty portfolio with the wide-open
APPROVED policy. VETOED scenario uses ``excluded_sectors=['Technology']``
so AAPL/Technology vetoes deterministically.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pandas as pd  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.graph.state import CompiledStateGraph  # noqa: E402
from langgraph.types import Command  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

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
from ai_hedge_fund.db.models import EpisodicMemory  # noqa: E402
from ai_hedge_fund.graph.memory_deps import MemoryDeps  # noqa: E402
from ai_hedge_fund.graph.pipeline import build_debate_pipeline  # noqa: E402
from ai_hedge_fund.graph.review_deps import ReviewDeps  # noqa: E402
from ai_hedge_fund.graph.risk_deps import RiskDeps  # noqa: E402
from ai_hedge_fund.output.portfolio_view import query_portfolio_view  # noqa: E402
from ai_hedge_fund.review.policy import ReviewPolicy, compute_review_policy_sha  # noqa: E402
from ai_hedge_fund.risk.policy import RiskPolicy  # noqa: E402

RISK_FIXTURES = Path(__file__).parent.parent / "risk" / "fixtures"
# Date inside the returns_golden.csv window (2024-01-02 .. 2024-12-18) so
# correlation + drawdown checks can evaluate a non-empty window.
AS_OF_IN_WINDOW = "2024-06-03"


# ---------------------------------------------------------------------------
# Stubbing helpers (duplicated minimally from test_phase7_e2e.py per 07-05
# SUMMARY decision 3 -- shared extraction to conftest deferred)
# ---------------------------------------------------------------------------


def _valid_bear_case() -> dict:
    """BearCase requires >=2 cross-linked claims. Mirrors Phase-7 stub."""
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


def _debate_synth_stub(confidence: int) -> dict:
    """DebateSynthesis stub carrying a ticker-agnostic revised_thesis.

    ``debate_synthesis_node`` overwrites ``state['thesis']`` with
    ``synthesis.revised_thesis`` so this dict controls the post-debate
    confidence that flows into the signal + FinalSignalOutput pipeline.
    """
    thesis = {
        "ticker": "AAPL",
        "bull_case": [
            {"claim": "c", "evidence": "e", "source_tool": "t"},
            {"claim": "c", "evidence": "e", "source_tool": "t"},
            {"claim": "c", "evidence": "e", "source_tool": "t"},
        ],
        "bear_case": [
            {"claim": "c", "evidence": "e", "source_tool": "t"},
            {"claim": "c", "evidence": "e", "source_tool": "t"},
            {"claim": "c", "evidence": "e", "source_tool": "t"},
        ],
        "confidence": confidence,
        "risk_factors": ["r1", "r2"],
    }
    return {
        "ticker": "AAPL",
        "revised_thesis": thesis,
        "pre_debate_confidence": confidence,
        "post_debate_confidence": confidence,
        "evidence_strength": 70,
        "logical_consistency": 70,
        "risk_coverage": 70,
        "quality_score": 70,
        "synthesis_notes": "stubbed synthesis",
    }


def _stubbed_stack(*, thesis_confidence: int = 85) -> ExitStack:
    """Override every LLM agent used by the Phase 5+6+7+8 pipeline.

    ``debate_synthesis`` is stubbed with a custom output whose
    ``revised_thesis.confidence`` drives the downstream conviction used by
    ``route_before_review`` -- above-threshold runs pass
    ``thesis_confidence=85`` (default), below-threshold ``thesis_confidence=50``.
    """
    stack = ExitStack()
    stack.enter_context(fundamental_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(sentiment_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(technical_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(manager_agent.override(model=TestModel()))
    stack.enter_context(bull_agent.override(model=TestModel()))
    stack.enter_context(
        bear_agent.override(model=TestModel(custom_output_args=_valid_bear_case()))
    )
    stack.enter_context(rebuttal_agent.override(model=TestModel()))
    stack.enter_context(final_arguments_agent.override(model=TestModel()))
    stack.enter_context(
        debate_synthesis_agent.override(
            model=TestModel(custom_output_args=_debate_synth_stub(thesis_confidence))
        )
    )
    stack.enter_context(
        risk_manager_agent.override(model=TestModel(custom_output_args={"rationale": "r"}))
    )
    stack.enter_context(signal_agent.override(model=TestModel()))
    stack.enter_context(
        self_critique_agent.override(model=TestModel(custom_output_args={"rationale": "r"}))
    )
    return stack


def _golden_returns() -> pd.DataFrame:
    return pd.read_csv(
        RISK_FIXTURES / "returns_golden.csv",
        index_col=0,
        parse_dates=True,
    )


def _wide_open_risk_policy() -> RiskPolicy:
    """Wide-open policy: empty portfolio + Consumer Staples candidate -> APPROVED."""
    return RiskPolicy(
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


def _build_pipeline(
    *,
    session: Session,
    beliefs_dir: Path,
    review_policy: ReviewPolicy,
    with_review: bool = True,
    risk_policy: RiskPolicy | None = None,
) -> CompiledStateGraph:
    risk_policy = risk_policy or _wide_open_risk_policy()
    # All e2e scenarios exercise the full Phase-8 stack -- build with
    # with_output=True and with_review=True (literal flags so the
    # phase-gate grep `grep -c "with_review=True"` catches the intent).
    if with_review:
        return build_debate_pipeline(
            checkpointer=InMemorySaver(),
            with_memory=True,
            memory_deps=MemoryDeps(db_session=session, beliefs_path=beliefs_dir),
            with_risk=True,
            risk_deps=RiskDeps(
                db_session=session, returns=_golden_returns(), policy=risk_policy
            ),
            with_output=True,
            with_review=True,
            review_deps=ReviewDeps(db_session=session, policy=review_policy),
        )
    return build_debate_pipeline(
        checkpointer=InMemorySaver(),
        with_memory=True,
        memory_deps=MemoryDeps(db_session=session, beliefs_path=beliefs_dir),
        with_risk=True,
        risk_deps=RiskDeps(
            db_session=session, returns=_golden_returns(), policy=risk_policy
        ),
        with_output=True,
        with_review=False,
        review_deps=ReviewDeps(db_session=session, policy=review_policy),
    )


def _initial_state(
    *,
    ticker: str = "PG",
    sector: str = "Consumer Staples",
    as_of: str = AS_OF_IN_WINDOW,
    threshold: int = 70,
) -> dict:
    return {
        "ticker": ticker,
        "as_of_date": as_of,
        "candidate_metadata": {"sector": sector, "instrument_type": "equity"},
        "_review_threshold": threshold,
    }


def _valid_decision(policy: ReviewPolicy, *, status: str = "APPROVED") -> dict:
    return {
        "status": status,
        "reviewer_id": "test-reviewer",
        "reviewer_note": f"{status.lower()} under test",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_policy_sha": compute_review_policy_sha(policy),
    }


# =====================================================================
# Scenarios
# =====================================================================


def test_above_threshold_fires_interrupt(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    review_policy: ReviewPolicy,
) -> None:
    """SIG-03: conviction >= threshold pauses the graph via LangGraph interrupt."""
    graph = _build_pipeline(
        session=memory_db_session,
        beliefs_dir=beliefs_tmp_dir,
        review_policy=review_policy,
    )
    cfg = {"configurable": {"thread_id": "test-above-1"}}
    with _stubbed_stack(thesis_confidence=85):
        result = asyncio.run(graph.ainvoke(_initial_state(threshold=70), config=cfg))

    interrupts = result.get("__interrupt__")
    assert interrupts, "conviction=85 >= threshold=70 must fire interrupt"
    payload = interrupts[0].value
    for key in (
        "ticker",
        "as_of_date",
        "signal",
        "thesis",
        "debate",
        "risk_assessment",
        "episodic_hits",
        "beliefs_consulted",
    ):
        assert key in payload


def test_below_threshold_skips_review(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    review_policy: ReviewPolicy,
) -> None:
    """SIG-03: conviction below threshold -> no interrupt; review_status=NOT_REQUIRED."""
    graph = _build_pipeline(
        session=memory_db_session,
        beliefs_dir=beliefs_tmp_dir,
        review_policy=review_policy,
    )
    cfg = {"configurable": {"thread_id": "test-below-1"}}
    with _stubbed_stack(thesis_confidence=50):
        result = asyncio.run(graph.ainvoke(_initial_state(threshold=70), config=cfg))

    assert result.get("__interrupt__") is None
    final_signal = result["final_signal"]
    assert final_signal["review_status"] == "NOT_REQUIRED"
    assert result.get("review_decision") is None


def test_approved_resume_completes(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    review_policy: ReviewPolicy,
) -> None:
    """SIG-03: Command(resume=ReviewDecision(APPROVED)) completes the pipeline."""
    graph = _build_pipeline(
        session=memory_db_session,
        beliefs_dir=beliefs_tmp_dir,
        review_policy=review_policy,
    )
    cfg = {"configurable": {"thread_id": "test-approved-1"}}
    with _stubbed_stack(thesis_confidence=85):
        asyncio.run(graph.ainvoke(_initial_state(threshold=70), config=cfg))
        final = asyncio.run(
            graph.ainvoke(
                Command(resume=_valid_decision(review_policy, status="APPROVED")),
                config=cfg,
            )
        )

    assert final["review_decision"]["status"] == "APPROVED"
    assert final["review_stored_id"] is not None
    review_rows = (
        memory_db_session.query(EpisodicMemory).filter_by(record_type="review").all()
    )
    assert len(review_rows) == 1
    assert review_rows[0].payload["review_status"] == "APPROVED"


def test_rejected_resume_persists_row_and_analysis_unchanged(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    review_policy: ReviewPolicy,
) -> None:
    """T-08-05: REJECTED resume writes review row; analysis row is byte-identical."""
    graph = _build_pipeline(
        session=memory_db_session,
        beliefs_dir=beliefs_tmp_dir,
        review_policy=review_policy,
    )
    cfg = {"configurable": {"thread_id": "test-rejected-1"}}
    with _stubbed_stack(thesis_confidence=85):
        paused = asyncio.run(graph.ainvoke(_initial_state(threshold=70), config=cfg))
        assert paused.get("__interrupt__")

        # Snapshot the analysis row BEFORE resume (episodic_store already wrote it)
        state = graph.get_state(cfg)
        analysis_id = state.values.get("episodic_stored_id")
        assert analysis_id is not None
        before_row = memory_db_session.get(EpisodicMemory, analysis_id)
        before_snapshot = {
            "payload": dict(before_row.payload),
            "signal_direction": before_row.signal_direction,
            "confidence": before_row.confidence,
            "record_type": before_row.record_type,
            "policy_sha": before_row.policy_sha,
        }

        final = asyncio.run(
            graph.ainvoke(
                Command(resume=_valid_decision(review_policy, status="REJECTED")),
                config=cfg,
            )
        )

    assert final["review_decision"]["status"] == "REJECTED"

    # Append-only: analysis row byte-identical
    memory_db_session.expire_all()
    after_row = memory_db_session.get(EpisodicMemory, analysis_id)
    assert after_row.payload == before_snapshot["payload"]
    assert after_row.signal_direction == before_snapshot["signal_direction"]
    assert after_row.confidence == before_snapshot["confidence"]
    assert after_row.record_type == before_snapshot["record_type"]
    assert after_row.policy_sha == before_snapshot["policy_sha"]

    review_rows = (
        memory_db_session.query(EpisodicMemory).filter_by(record_type="review").all()
    )
    assert len(review_rows) == 1
    assert review_rows[0].payload["review_status"] == "REJECTED"


def test_vetoed_never_reaches_review(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    review_policy: ReviewPolicy,
) -> None:
    """T-08-06: VETOED path MUST NOT surface an interrupt or write a review row.

    Uses ``excluded_sectors=['Technology']`` + AAPL/Technology so the
    first-violation-wins exclusion check fires deterministically. The VETOED
    risk_manager routes to episodic_store; output_node then short-circuits
    (no signal); human_review_node short-circuits on error; review_store_node
    short-circuits on error -- no review row written.
    """
    vetoed_policy = _wide_open_risk_policy().model_copy(
        update={"excluded_sectors": ["Technology"]}
    )

    graph = _build_pipeline(
        session=memory_db_session,
        beliefs_dir=beliefs_tmp_dir,
        review_policy=review_policy,
        risk_policy=vetoed_policy,
    )
    cfg = {"configurable": {"thread_id": "test-vetoed-1"}}
    with _stubbed_stack(thesis_confidence=85):
        result = asyncio.run(
            graph.ainvoke(
                _initial_state(
                    ticker="AAPL", sector="Technology", threshold=70
                ),
                config=cfg,
            )
        )

    assert result.get("__interrupt__") is None
    assert result.get("review_decision") is None
    assert result.get("final_signal") is None  # output_node short-circuited

    review_rows = (
        memory_db_session.query(EpisodicMemory).filter_by(record_type="review").all()
    )
    assert len(review_rows) == 0

    # Analysis (VETOED) row still written by Phase-7 episodic_store_node
    analysis_rows = (
        memory_db_session.query(EpisodicMemory).filter_by(record_type="analysis").all()
    )
    assert len(analysis_rows) == 1
    assert analysis_rows[0].payload["risk_assessment"]["status"] == "VETOED"


def test_not_required_path_writes_review_row_uniform_audit(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    review_policy: ReviewPolicy,
) -> None:
    """Below-threshold path still writes a record_type='review' row with
    status='NOT_REQUIRED' -- audit trail is uniform across all non-VETOED
    paths (Pitfall G)."""
    graph = _build_pipeline(
        session=memory_db_session,
        beliefs_dir=beliefs_tmp_dir,
        review_policy=review_policy,
    )
    cfg = {"configurable": {"thread_id": "test-uniform-1"}}
    with _stubbed_stack(thesis_confidence=50):
        asyncio.run(graph.ainvoke(_initial_state(threshold=70), config=cfg))

    review_rows = (
        memory_db_session.query(EpisodicMemory).filter_by(record_type="review").all()
    )
    assert len(review_rows) == 1
    assert review_rows[0].payload["review_status"] == "NOT_REQUIRED"


def test_portfolio_view_freshness_after_run(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    review_policy: ReviewPolicy,
) -> None:
    """SIG-02: running the pipeline makes the ticker visible in portfolio view
    immediately, with no cache invalidation."""
    # Before: empty DB -> empty view
    view_before = query_portfolio_view(memory_db_session, as_of_date="2026-04-20")
    tickers_before = {e["ticker"] for s in view_before.values() for e in s}
    assert "PG" not in tickers_before

    graph = _build_pipeline(
        session=memory_db_session,
        beliefs_dir=beliefs_tmp_dir,
        review_policy=review_policy,
    )
    cfg = {"configurable": {"thread_id": "test-fresh-1"}}
    with _stubbed_stack(thesis_confidence=50):
        asyncio.run(graph.ainvoke(_initial_state(threshold=70), config=cfg))

    # After: same query, no refresh call -> ticker now visible
    view_after = query_portfolio_view(memory_db_session, as_of_date="2026-04-20")
    tickers_after = {e["ticker"] for s in view_after.values() for e in s}
    assert "PG" in tickers_after
    # And it appears under the correct sector
    assert "Consumer Staples" in view_after
    pg_entries = [e for e in view_after["Consumer Staples"] if e["ticker"] == "PG"]
    assert len(pg_entries) == 1


def test_phase5_backcompat_no_kwargs_still_compiles() -> None:
    """Phase-5 topology unchanged when no Phase 6/7/8 flags are set."""
    graph = build_debate_pipeline()
    nodes = set(graph.get_graph().nodes)
    expected_phase5_nodes = {
        "fundamental",
        "sentiment",
        "technical",
        "manager",
        "bull",
        "bear",
        "rebuttal",
        "final_arguments",
        "debate_synthesis",
        "signal",
    }
    # All Phase-5 nodes present
    assert expected_phase5_nodes.issubset(nodes)
    # No Phase 6/7/8 nodes
    for later in (
        "risk_manager",
        "memory_recall",
        "episodic_store",
        "output",
        "human_review",
        "review_store",
    ):
        assert later not in nodes
