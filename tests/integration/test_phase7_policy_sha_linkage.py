"""Phase 6 -> Phase 7 policy_sha audit linkage tests.

Mirrors ``tests/integration/test_policy_sha_audit.py`` (Phase 6) -- same
six-scenario structure (determinism, change-sensitivity, idempotence,
format on APPROVED, format on VETOED, three-way cross-layer equality).
All assertions target :attr:`EpisodicMemory.policy_sha` (Phase 7 column)
vs. the :class:`RiskAssessment.policy_sha` (Phase 6) produced by the
same pipeline run.

All 12 agents stubbed via :class:`TestModel`. Zero real LLM calls.
"""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import ExitStack
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
from ai_hedge_fund.memory import seed_episodic_from_csv  # noqa: E402
from ai_hedge_fund.risk.policy import RiskPolicy, compute_policy_sha, load_policy  # noqa: E402
from ai_hedge_fund.risk.portfolio import seed_portfolio_from_csv  # noqa: E402

RISK_FIXTURES = Path(__file__).parent.parent / "risk" / "fixtures"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Stubbing helpers (duplicated minimally from test_phase7_e2e.py; shared
# extraction to tests/integration/conftest.py is deferred pending a future
# refactor)
# ---------------------------------------------------------------------------


def _valid_bear_case() -> dict:
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


def _run(
    session: Session,
    beliefs_dir: Path,
    policy: RiskPolicy,
    *,
    ticker: str = "PG",
    sector: str = "Consumer Staples",
) -> dict[str, Any]:
    """Run the composed pipeline once and return the final state."""
    risk_deps = RiskDeps(db_session=session, returns=_golden_returns(), policy=policy)
    memory_deps = MemoryDeps(db_session=session, beliefs_path=beliefs_dir)
    graph = build_debate_pipeline(
        with_risk=True,
        risk_deps=risk_deps,
        with_memory=True,
        memory_deps=memory_deps,
    )
    with _stubbed_stack():
        initial = {
            "ticker": ticker,
            "as_of_date": "2026-03-01",
            "candidate_metadata": {"sector": sector, "instrument_type": "equity"},
        }
        return asyncio.run(graph.ainvoke(initial))


# ---------------------------------------------------------------------------
# Test 1 — same policy => identical policy_sha across two runs
# ---------------------------------------------------------------------------


def test_same_policy_same_episodic_sha(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    seed_portfolio_from_csv(memory_db_session, RISK_FIXTURES / "portfolio_sample.csv", "2026-03-01")
    policy = load_policy(RISK_FIXTURES / "risk_policy_sample.yaml")

    state1 = _run(memory_db_session, beliefs_tmp_dir, policy)
    row1 = memory_db_session.query(EpisodicMemory).filter_by(id=state1["episodic_stored_id"]).one()
    state2 = _run(memory_db_session, beliefs_tmp_dir, policy)
    row2 = memory_db_session.query(EpisodicMemory).filter_by(id=state2["episodic_stored_id"]).one()

    expected = compute_policy_sha(policy)
    assert row1.policy_sha == expected
    assert row2.policy_sha == expected
    assert row1.policy_sha == row2.policy_sha


# ---------------------------------------------------------------------------
# Test 2 — different policies => different policy_sha on stored row
# ---------------------------------------------------------------------------


def test_different_policy_different_episodic_sha(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    seed_portfolio_from_csv(memory_db_session, RISK_FIXTURES / "portfolio_sample.csv", "2026-03-01")
    policy_a = load_policy(RISK_FIXTURES / "risk_policy_sample.yaml")
    policy_b = policy_a.model_copy(
        update={"max_single_position_pct": policy_a.max_single_position_pct + 1.0}
    )

    state1 = _run(memory_db_session, beliefs_tmp_dir, policy_a)
    state2 = _run(memory_db_session, beliefs_tmp_dir, policy_b)
    row1 = memory_db_session.query(EpisodicMemory).filter_by(id=state1["episodic_stored_id"]).one()
    row2 = memory_db_session.query(EpisodicMemory).filter_by(id=state2["episodic_stored_id"]).one()

    assert row1.policy_sha != row2.policy_sha
    assert SHA_RE.fullmatch(row1.policy_sha)
    assert SHA_RE.fullmatch(row2.policy_sha)


# ---------------------------------------------------------------------------
# Test 3 — idempotence under revert: A, A', A => runs 1 and 3 identical
# ---------------------------------------------------------------------------


def test_idempotent_revert(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    seed_portfolio_from_csv(memory_db_session, RISK_FIXTURES / "portfolio_sample.csv", "2026-03-01")
    policy_a = load_policy(RISK_FIXTURES / "risk_policy_sample.yaml")
    policy_b = policy_a.model_copy(
        update={"max_single_position_pct": policy_a.max_single_position_pct + 1.0}
    )

    state1 = _run(memory_db_session, beliefs_tmp_dir, policy_a)
    state2 = _run(memory_db_session, beliefs_tmp_dir, policy_b)
    state3 = _run(memory_db_session, beliefs_tmp_dir, policy_a)

    rows = [
        memory_db_session.query(EpisodicMemory).filter_by(id=s["episodic_stored_id"]).one()
        for s in (state1, state2, state3)
    ]
    assert rows[0].policy_sha == rows[2].policy_sha
    assert rows[0].policy_sha != rows[1].policy_sha


# ---------------------------------------------------------------------------
# Test 4 — policy_sha on APPROVED row is 64-char lowercase hex
# ---------------------------------------------------------------------------


def test_sha_format_on_approved(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    seed_portfolio_from_csv(memory_db_session, RISK_FIXTURES / "portfolio_sample.csv", "2026-03-01")
    policy = load_policy(RISK_FIXTURES / "risk_policy_sample.yaml")

    state = _run(memory_db_session, beliefs_tmp_dir, policy)
    assert state["risk_assessment"]["status"] == "APPROVED"
    row = memory_db_session.query(EpisodicMemory).filter_by(id=state["episodic_stored_id"]).one()
    assert SHA_RE.fullmatch(row.policy_sha)
    # Defense-in-depth: the column value is pure lowercase hex
    assert row.policy_sha == row.policy_sha.lower()


# ---------------------------------------------------------------------------
# Test 5 — policy_sha on VETOED row is also well-formed
# ---------------------------------------------------------------------------


def test_sha_format_on_vetoed(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    seed_portfolio_from_csv(memory_db_session, RISK_FIXTURES / "portfolio_sample.csv", "2026-03-01")
    base_policy = load_policy(RISK_FIXTURES / "risk_policy_sample.yaml")
    # Exclude Technology so AAPL (Technology) triggers VETO deterministically.
    veto_policy = base_policy.model_copy(update={"excluded_sectors": ["Technology"]})

    state = _run(
        memory_db_session,
        beliefs_tmp_dir,
        veto_policy,
        ticker="AAPL",
        sector="Technology",
    )
    assert state["risk_assessment"]["status"] == "VETOED"
    row = memory_db_session.query(EpisodicMemory).filter_by(id=state["episodic_stored_id"]).one()
    assert SHA_RE.fullmatch(row.policy_sha)


# ---------------------------------------------------------------------------
# Test 6 — three-way equality: state, column, payload all agree
# ---------------------------------------------------------------------------


def test_three_way_sha_equality(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """state['risk_assessment']['policy_sha'] == row.policy_sha == row.payload[...].policy_sha.

    Any layer silently rewriting the SHA would break this equality. Locks
    the cross-phase audit contract end-to-end.
    """
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    seed_portfolio_from_csv(memory_db_session, RISK_FIXTURES / "portfolio_sample.csv", "2026-03-01")
    policy = load_policy(RISK_FIXTURES / "risk_policy_sample.yaml")

    state = _run(memory_db_session, beliefs_tmp_dir, policy)
    row = memory_db_session.query(EpisodicMemory).filter_by(id=state["episodic_stored_id"]).one()
    assert state["risk_assessment"]["policy_sha"] == row.policy_sha
    assert row.payload["risk_assessment"]["policy_sha"] == row.policy_sha
    # And all three equal the canonical hash of the fixture policy.
    assert row.policy_sha == compute_policy_sha(policy)
