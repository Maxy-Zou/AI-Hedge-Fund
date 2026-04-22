"""Phase 7 end-to-end scenarios — MEM-01..04 integration tests.

All 12 agents (11 debate/risk + self_critique) stubbed via TestModel.
Zero real LLM calls. Consumes memory fixtures via ``tests/integration/
conftest.py`` which re-exports them from ``tests/memory/conftest.py``, and
risk fixtures directly from ``tests/risk/fixtures/`` (portfolio + policy +
returns).

Scenarios:
    1. with_memory only: episodic recall + belief read + episodic store
    2. with_memory + with_risk: policy_sha audit linkage
    3. VETOED persistence: Open Question 1 ratified
    4. MEM-03 read: human-edited belief survives the pipeline
    5. MEM-04 write: ingest_outcome updates belief (plain)
    6. MEM-03 × MEM-04: human-edited belief survives ingest_outcome
    7. Temporal correctness (Pitfall 2 regression)
    8. Phase-5 backcompat smoke
"""

from __future__ import annotations

import asyncio
import os
import shutil
from contextlib import ExitStack
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pandas as pd  # noqa: E402
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
from ai_hedge_fund.graph.risk_deps import RiskDeps  # noqa: E402
from ai_hedge_fund.memory import load_belief, seed_episodic_from_csv  # noqa: E402
from ai_hedge_fund.risk.policy import load_policy  # noqa: E402
from ai_hedge_fund.risk.portfolio import seed_portfolio_from_csv  # noqa: E402
from ai_hedge_fund.scripts.ingest_outcome import ingest_outcome  # noqa: E402

RISK_FIXTURES = Path(__file__).parent.parent / "risk" / "fixtures"


# ---------------------------------------------------------------------------
# Stubbing helpers: all 12 agents must be overridden for every pipeline run
# ---------------------------------------------------------------------------


def _valid_bear_case() -> dict:
    """BearCase requires >=2 claims that cross-link to bull claims (WR-01)."""
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


def _stubbed_stack(*, rationale: str = "stubbed risk rationale") -> ExitStack:
    """Return an ExitStack overriding every LLM agent used by the pipeline.

    Includes self_critique_agent so MEM-04 ingest_outcome calls in the same
    test body work under the same zero-LLM-call contract.
    """
    stack = ExitStack()
    stack.enter_context(fundamental_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(sentiment_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(technical_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(manager_agent.override(model=TestModel()))
    stack.enter_context(bull_agent.override(model=TestModel()))
    stack.enter_context(bear_agent.override(model=TestModel(custom_output_args=_valid_bear_case())))
    stack.enter_context(rebuttal_agent.override(model=TestModel()))
    stack.enter_context(final_arguments_agent.override(model=TestModel()))
    stack.enter_context(debate_synthesis_agent.override(model=TestModel()))
    stack.enter_context(
        risk_manager_agent.override(model=TestModel(custom_output_args={"rationale": rationale}))
    )
    stack.enter_context(signal_agent.override(model=TestModel()))
    stack.enter_context(
        self_critique_agent.override(
            model=TestModel(custom_output_args={"rationale": "stubbed MEM-04 rationale"})
        )
    )
    return stack


def _initial_state(
    ticker: str = "AAPL",
    as_of: str = "2026-04-20",
    sector: str = "Technology",
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "as_of_date": as_of,
        "candidate_metadata": {"sector": sector, "instrument_type": "equity"},
    }


def _golden_returns() -> pd.DataFrame:
    return pd.read_csv(
        RISK_FIXTURES / "returns_golden.csv",
        index_col=0,
        parse_dates=True,
    )


# ---------------------------------------------------------------------------
# Test 1: with_memory alone — episodic recall + belief read + episodic store
# ---------------------------------------------------------------------------


def test_with_memory_loads_episodic_hits_and_beliefs(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """MEM-01 read path + MEM-02 belief read + MEM-01 write path end-to-end."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    memory_deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(with_memory=True, memory_deps=memory_deps)

    with _stubbed_stack():
        final_state = asyncio.run(graph.ainvoke(_initial_state()))

    assert final_state.get("error") is None, f"Pipeline errored: {final_state.get('error')}"
    # MEM-01 read: hits present, all temporal-filter-respecting
    assert final_state.get("episodic_hits"), "episodic_hits should be non-empty"
    for hit in final_state["episodic_hits"]:
        assert hit["as_of_date"][:10] <= "2026-04-20", (
            f"Hit dated after cutoff: {hit['as_of_date']}"
        )
    # MEM-02 belief read: ticker-level AAPL belief consulted
    assert final_state.get("beliefs_consulted"), "beliefs_consulted should be non-empty"
    aapl_beliefs = [b for b in final_state["beliefs_consulted"] if b["ticker"] == "AAPL"]
    assert len(aapl_beliefs) >= 1, "Expected at least one AAPL belief in beliefs_consulted"
    # MEM-01 write: new episodic row landed
    stored_id = final_state.get("episodic_stored_id")
    assert isinstance(stored_id, int) and stored_id > 0
    row = memory_db_session.query(EpisodicMemory).filter_by(id=stored_id).one()
    assert row.record_type == "analysis"
    assert row.ticker == "AAPL"


# ---------------------------------------------------------------------------
# Test 2: composed with_memory + with_risk — policy_sha audit linkage
# ---------------------------------------------------------------------------


def test_composed_with_risk_persists_episodic_with_policy_sha(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """Phase 6 -> Phase 7 audit: stored row's policy_sha == state's policy_sha."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    seed_portfolio_from_csv(memory_db_session, RISK_FIXTURES / "portfolio_sample.csv", "2026-03-01")
    policy = load_policy(RISK_FIXTURES / "risk_policy_sample.yaml")
    risk_deps = RiskDeps(db_session=memory_db_session, returns=_golden_returns(), policy=policy)
    memory_deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(
        with_risk=True,
        risk_deps=risk_deps,
        with_memory=True,
        memory_deps=memory_deps,
    )

    with _stubbed_stack():
        # PG (Consumer Staples) + default policy -> APPROVED path
        state = _initial_state(ticker="PG", as_of="2026-03-01", sector="Consumer Staples")
        final_state = asyncio.run(graph.ainvoke(state))

    assert final_state.get("error") is None, f"Pipeline errored: {final_state.get('error')}"
    risk_assessment = final_state.get("risk_assessment")
    assert risk_assessment is not None
    expected_sha = risk_assessment.get("policy_sha")
    assert expected_sha, "policy_sha required on risk_assessment"
    stored_id = final_state.get("episodic_stored_id")
    assert isinstance(stored_id, int)
    row = memory_db_session.query(EpisodicMemory).filter_by(id=stored_id).one()
    # The cross-phase audit link: column + payload both agree
    assert row.policy_sha == expected_sha
    assert row.payload["risk_assessment"]["policy_sha"] == expected_sha


# ---------------------------------------------------------------------------
# Test 3: VETOED persistence — Open Question 1 ratified end-to-end
# ---------------------------------------------------------------------------


def test_vetoed_decision_is_persisted_end_to_end(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """A vetoed run STILL stores an episodic row; signal is None (Pitfall 8)."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    seed_portfolio_from_csv(memory_db_session, RISK_FIXTURES / "portfolio_sample.csv", "2026-03-01")
    # Custom policy: exclude Technology so AAPL candidate -> VETOED
    base_policy = load_policy(RISK_FIXTURES / "risk_policy_sample.yaml")
    veto_policy = base_policy.model_copy(update={"excluded_sectors": ["Technology"]})
    risk_deps = RiskDeps(
        db_session=memory_db_session, returns=_golden_returns(), policy=veto_policy
    )
    memory_deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(
        with_risk=True,
        risk_deps=risk_deps,
        with_memory=True,
        memory_deps=memory_deps,
    )

    with _stubbed_stack():
        state = _initial_state(ticker="AAPL", as_of="2026-03-01", sector="Technology")
        final_state = asyncio.run(graph.ainvoke(state))

    assert final_state.get("error") is None
    assert final_state["risk_assessment"]["status"] == "VETOED"
    # Pitfall 8: no signal on veto
    assert final_state.get("signal") is None
    # Open Question 1: the row IS still persisted
    stored_id = final_state.get("episodic_stored_id")
    assert isinstance(stored_id, int)
    row = memory_db_session.query(EpisodicMemory).filter_by(id=stored_id).one()
    assert row.payload["risk_assessment"]["status"] == "VETOED"
    assert row.signal_direction is None
    # policy_sha still present on a vetoed row (used by linkage tests later)
    assert row.policy_sha


# ---------------------------------------------------------------------------
# Test 4: MEM-03 read — human-edited belief survives pipeline read
# ---------------------------------------------------------------------------


def test_human_edited_belief_survives_pipeline_read(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """Human-edited confidence=20 + human_edited=true reach state['beliefs_consulted']."""
    # Replace plain AAPL.yaml with the human-edited variant BEFORE the run.
    shutil.copy2(
        beliefs_tmp_dir / "tickers" / "AAPL_human.yaml",
        beliefs_tmp_dir / "tickers" / "AAPL.yaml",
    )
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    memory_deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(with_memory=True, memory_deps=memory_deps)

    with _stubbed_stack():
        final_state = asyncio.run(graph.ainvoke(_initial_state()))

    aapl_beliefs = [
        b for b in (final_state.get("beliefs_consulted") or []) if b["ticker"] == "AAPL"
    ]
    assert len(aapl_beliefs) == 1
    assert aapl_beliefs[0]["human_edited"] is True
    assert aapl_beliefs[0]["confidence"] == 20


# ---------------------------------------------------------------------------
# Test 5: MEM-04 full write loop — ingest_outcome updates plain belief
# ---------------------------------------------------------------------------


def test_outcome_ingest_updates_plain_belief(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
) -> None:
    """+4.2% outcome on a long analysis: confidence 72 -> 82 (cap 10)."""
    # Seed a linked analysis row so signal_direction propagates to outcome row.
    memory_db_session.add(
        EpisodicMemory(
            ticker="AAPL",
            sector="Technology",
            record_type="analysis",
            signal_direction="long",
            confidence=72,
            policy_sha="z" * 64,
            as_of_date=datetime(2026, 1, 10, tzinfo=UTC),
            payload={"schema_version": 1},
        )
    )
    memory_db_session.commit()

    with _stubbed_stack():
        result = asyncio.run(
            ingest_outcome(
                session=memory_db_session,
                beliefs_dir=beliefs_tmp_dir,
                ticker="AAPL",
                outcome_pct=+4.2,
                as_of_date=date(2026, 4, 20),
            )
        )

    assert result["outcome_row_id"] > 0
    # compute_new_confidence(72, +4.2, "long") = 72 + min(0.3*4.2*10, 10) = 72 + 10 = 82
    fresh_belief, _ = load_belief(beliefs_tmp_dir / "tickers" / "AAPL.yaml")
    assert fresh_belief.confidence == 82
    assert len(fresh_belief.critique_history) >= 1
    last_entry = fresh_belief.critique_history[-1]
    assert last_entry.rationale == "stubbed MEM-04 rationale"
    assert last_entry.source == "self_critique"


# ---------------------------------------------------------------------------
# Test 6: MEM-03 × MEM-04 — human-edited belief survives ingest_outcome
# ---------------------------------------------------------------------------


def test_outcome_ingest_preserves_human_edited_belief(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
) -> None:
    """Human-pinned confidence=20 stays 20; outcome row + critique_history still land."""
    shutil.copy2(
        beliefs_tmp_dir / "tickers" / "AAPL_human.yaml",
        beliefs_tmp_dir / "tickers" / "AAPL.yaml",
    )
    memory_db_session.add(
        EpisodicMemory(
            ticker="AAPL",
            sector="Technology",
            record_type="analysis",
            signal_direction="long",
            confidence=20,
            as_of_date=datetime(2026, 1, 10, tzinfo=UTC),
            payload={"schema_version": 1},
        )
    )
    memory_db_session.commit()

    with _stubbed_stack():
        result = asyncio.run(
            ingest_outcome(
                session=memory_db_session,
                beliefs_dir=beliefs_tmp_dir,
                ticker="AAPL",
                outcome_pct=+4.2,
                as_of_date=date(2026, 4, 20),
            )
        )

    # Confidence UNCHANGED: human-edit guard fires
    fresh_belief, _ = load_belief(beliefs_tmp_dir / "tickers" / "AAPL.yaml")
    assert fresh_belief.confidence == 20
    # Skip audited via structured reason
    assert result["skipped"].get("confidence") == "human_edited_global_flag_set"
    # But critique_history IS updated (audit trail matters)
    assert "critique_history" in result["applied"]
    # And the outcome row still landed
    outcome_rows = (
        memory_db_session.query(EpisodicMemory)
        .filter_by(record_type="outcome", ticker="AAPL")
        .count()
    )
    assert outcome_rows == 1


# ---------------------------------------------------------------------------
# Test 7: temporal correctness at pipeline level (Pitfall 2 regression)
# ---------------------------------------------------------------------------


def test_pipeline_never_returns_future_dated_episodic_hits(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """Seed FUTUREX at 2099-01-01; query cutoff 2026-06-01 must not return it."""
    # seeded_episodic.csv includes FUTUREX at 2099-01-01.
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    memory_deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(with_memory=True, memory_deps=memory_deps)

    with _stubbed_stack():
        state = _initial_state(ticker="FUTUREX", as_of="2026-06-01", sector="Technology")
        final_state = asyncio.run(graph.ainvoke(state))

    hits = final_state.get("episodic_hits") or []
    for hit in hits:
        assert not str(hit["as_of_date"]).startswith("2099"), f"Future-dated row leaked: {hit}"


# ---------------------------------------------------------------------------
# Test 8: Phase-5 backcompat smoke — no kwargs still compiles
# ---------------------------------------------------------------------------


def test_phase5_backcompat_no_kwargs_still_compiles() -> None:
    """``build_debate_pipeline()`` has zero memory/risk nodes by default."""
    graph = build_debate_pipeline()
    node_names = set(graph.get_graph().nodes)
    assert "memory_recall" not in node_names
    assert "episodic_store" not in node_names
    assert "risk_manager" not in node_names
    # Phase-5 analysts + debate chain intact
    assert {
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
    }.issubset(node_names)
