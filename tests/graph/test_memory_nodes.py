"""Tests for MemoryDeps, memory_recall_node, and episodic_store_node (07-03).

Structure mirrors ``tests/graph/test_risk_node.py``:
- Task-1 block: MemoryDeps immutability + DebatePipelineState schema introspection.
- Task-2 block: memory_recall_node + episodic_store_node behaviour (short-circuit,
  temporal filter, MEM-03 read path, VETOED persistence, missing-belief tolerance).

No real LLM calls. Fixtures come from ``tests/memory/conftest.py`` via the
re-export shim in ``tests/graph/conftest.py``.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, get_type_hints

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pytest  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ai_hedge_fund.db.models import EpisodicMemory  # noqa: E402
from ai_hedge_fund.graph.memory_deps import MemoryDeps  # noqa: E402
from ai_hedge_fund.graph.nodes import episodic_store_node, memory_recall_node  # noqa: E402
from ai_hedge_fund.memory.episodic import seed_episodic_from_csv  # noqa: E402
from ai_hedge_fund.schemas.state import DebatePipelineState  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers (Task 2+)
# ---------------------------------------------------------------------------


def _run_recall(state: Any, deps: MemoryDeps) -> dict:
    return asyncio.run(memory_recall_node(state, deps))


def _run_store(state: Any, deps: MemoryDeps) -> dict:
    return asyncio.run(episodic_store_node(state, deps))


def _base_state(
    ticker: str = "AAPL",
    as_of_date: str = "2026-04-20",
    sector: str | None = "Technology",
) -> dict:
    out: dict = {"ticker": ticker, "as_of_date": as_of_date}
    if sector is not None:
        out["candidate_metadata"] = {"sector": sector, "instrument_type": "equity"}
    return out


def _post_debate_state(
    *,
    ticker: str = "AAPL",
    as_of_date: str = "2026-04-20",
    sector: str = "Technology",
    confidence: int = 70,
    signal_direction: str | None = "long",
    risk_status: str | None = "APPROVED",
    policy_sha: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
) -> dict:
    """Build a DebatePipelineState post-debate (thesis + signal + risk filled)."""
    state: dict = {
        "ticker": ticker,
        "as_of_date": as_of_date,
        "candidate_metadata": {"sector": sector, "instrument_type": "equity"},
        "thesis": {
            "ticker": ticker,
            "bull_case": ["b1", "b2"],
            "bear_case": ["r1", "r2"],
            "confidence": confidence,
            "risk_factors": [],
        },
    }
    if signal_direction is not None:
        state["signal"] = {
            "ticker": ticker,
            "direction": signal_direction,
            "conviction": "medium",
            "rationale": "test",
        }
    else:
        state["signal"] = None
    if risk_status is not None:
        state["risk_assessment"] = {
            "ticker": ticker,
            "status": risk_status,
            "constraint_violated": None if risk_status == "APPROVED" else "max_sector_pct",
            "observed": None if risk_status == "APPROVED" else 0.5,
            "limit": None if risk_status == "APPROVED" else 0.3,
            "rationale": "stub rationale",
            "policy_sha": policy_sha,
        }
    return state


# ---------------------------------------------------------------------------
# Task 1 — MemoryDeps + DebatePipelineState schema
# ---------------------------------------------------------------------------


def test_memory_deps_is_frozen(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    assert deps.recall_limit == 10
    with pytest.raises(FrozenInstanceError):
        deps.recall_limit = 5  # type: ignore[misc]


def test_memory_deps_accepts_custom_recall_limit(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    deps = MemoryDeps(
        db_session=memory_db_session,
        beliefs_path=beliefs_tmp_dir,
        recall_limit=3,
    )
    assert deps.recall_limit == 3


def test_debate_pipeline_state_has_memory_keys() -> None:
    hints = get_type_hints(DebatePipelineState)
    assert "episodic_hits" in hints
    assert "beliefs_consulted" in hints
    assert "episodic_stored_id" in hints


def test_memory_state_keys_are_single_writer() -> None:
    """Single-writer means no ``Annotated[..., operator.add]`` reducer.

    A reducer on these keys would silently accumulate across writers; there
    are no parallel writers in the 07-03 topology, but we lock the invariant
    so a future hand cannot introduce one without updating this test.
    """
    hints = get_type_hints(DebatePipelineState, include_extras=True)
    for key in ("episodic_hits", "beliefs_consulted", "episodic_stored_id"):
        hint = hints[key]
        assert not hasattr(hint, "__metadata__"), (
            f"{key} must be single-writer (no Annotated reducer)"
        )


# ---------------------------------------------------------------------------
# Task 2 — memory_recall_node (tests 6-10, 15)
# ---------------------------------------------------------------------------


def test_memory_recall_short_circuits_on_upstream_error(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """Test 6: state['error'] set -> node returns {} without DB access."""
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    state = _base_state()
    state["error"] = "prior failure"
    assert _run_recall(state, deps) == {}


def test_memory_recall_returns_hits_filtered_by_ticker_and_sector(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """Test 7: seeded AAPL rows + Tech sector rows come back via OR predicate.

    The seed has AAPL analysis+outcome, MSFT analysis+outcome (both Tech),
    and JNJ (Healthcare). With ticker=AAPL AND sector=Technology we expect
    both AAPL + MSFT entries (Tech sector) but NOT JNJ.
    """
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    state = _base_state(ticker="AAPL", as_of_date="2026-04-20", sector="Technology")
    result = _run_recall(state, deps)

    hits = result["episodic_hits"]
    assert isinstance(hits, list)
    assert len(hits) >= 2  # AAPL + MSFT analyses + outcomes
    # Every hit is a dict (EpisodicHit.model_dump(mode='json')), not a model.
    assert all(isinstance(h, dict) for h in hits)
    # No JNJ (Healthcare) in the result set.
    tickers = {h["ticker"] for h in hits}
    assert "JNJ" not in tickers
    # DESC order by as_of_date: each subsequent hit's date <= previous.
    dates = [h["as_of_date"] for h in hits]
    assert dates == sorted(dates, reverse=True)


def test_memory_recall_excludes_future_dated_row_pitfall_2(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """Test 8: Pitfall 2 regression at graph level -- FUTUREX 2099-01-01 row
    is NEVER returned by a recall with an earlier as_of_date target.
    """
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    state = _base_state(ticker="FUTUREX", as_of_date="2026-06-01", sector="Technology")
    result = _run_recall(state, deps)

    tickers = {h["ticker"] for h in result["episodic_hits"]}
    assert "FUTUREX" not in tickers  # PITFALL-2 REGRESSION


def test_memory_recall_preserves_human_edited_belief_mem03_read(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """Test 9 (MEM-03 read path): human-edited belief reaches state untouched.

    Copies the human-edited variant over AAPL.yaml; the loaded belief MUST
    carry human_edited=True and confidence=20 (the human override).
    """
    shutil.copy2(
        beliefs_tmp_dir / "tickers" / "AAPL_human.yaml",
        beliefs_tmp_dir / "tickers" / "AAPL.yaml",
    )
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    state = _base_state(ticker="AAPL", as_of_date="2026-04-20", sector="Technology")
    result = _run_recall(state, deps)

    beliefs = result["beliefs_consulted"]
    assert isinstance(beliefs, list)
    aapl_beliefs = [b for b in beliefs if b["ticker"] == "AAPL"]
    assert len(aapl_beliefs) == 1
    assert aapl_beliefs[0]["human_edited"] is True
    assert aapl_beliefs[0]["confidence"] == 20
    # Belief.model_dump(mode="json") serialises date to ISO string; the
    # fixture pins edited_at to 2026-04-18.
    assert aapl_beliefs[0]["edited_at"] == "2026-04-18"


def test_memory_recall_or_composition_ticker_plus_sector(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """Test 10: ticker=AAPL + sector=Technology returns AAPL rows AND MSFT
    (sector match). JNJ (Healthcare) must NOT appear.
    """
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    state = _base_state(ticker="AAPL", as_of_date="2026-04-20", sector="Technology")
    result = _run_recall(state, deps)

    tickers = {h["ticker"] for h in result["episodic_hits"]}
    assert "AAPL" in tickers  # ticker match
    assert "MSFT" in tickers  # sector match (Technology, ticker != AAPL)
    assert "JNJ" not in tickers  # Healthcare, must not appear


def test_memory_recall_missing_belief_file_is_not_fatal(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """Test 15: beliefs_path/tickers/UNKNOWN.yaml does not exist -> empty
    beliefs_consulted list, not FileNotFoundError.
    """
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    # Use a ticker that is NOT on disk; note UNKNOWN is valid-format.
    state = _base_state(ticker="UNKNOWN", as_of_date="2026-04-20", sector="Technology")
    result = _run_recall(state, deps)

    assert result["beliefs_consulted"] == []


# ---------------------------------------------------------------------------
# Task 2 — episodic_store_node (tests 11-14)
# ---------------------------------------------------------------------------


def test_episodic_store_inserts_row_with_policy_sha_link(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """Test 11: store inserts an EpisodicMemory row with all fields populated
    and returns {'episodic_stored_id': <int>}.
    """
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    state = _post_debate_state()
    result = _run_store(state, deps)

    assert "episodic_stored_id" in result
    row_id = result["episodic_stored_id"]
    assert isinstance(row_id, int)

    row = memory_db_session.query(EpisodicMemory).filter_by(id=row_id).one()
    assert row.ticker == "AAPL"
    assert row.sector == "Technology"
    assert row.record_type == "analysis"
    assert row.signal_direction == "long"
    assert row.confidence == 70
    assert row.outcome_pct is None
    assert row.policy_sha == ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    assert row.payload["thesis"]["confidence"] == 70
    assert row.payload["signal"]["direction"] == "long"
    assert row.payload["risk_assessment"]["status"] == "APPROVED"


def test_episodic_store_policy_sha_authoritative_column_matches_payload(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """Test 12: policy_sha authoritative copy.

    row.policy_sha column IS authoritative. The payload copy is convenience.
    After a single write, the two values must be byte-for-byte equal.
    """
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    expected_sha = "a3f5c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852c011"
    state = _post_debate_state(policy_sha=expected_sha)
    result = _run_store(state, deps)

    row = memory_db_session.query(EpisodicMemory).filter_by(id=result["episodic_stored_id"]).one()
    assert row.policy_sha == expected_sha
    assert row.payload["risk_assessment"]["policy_sha"] == expected_sha
    assert row.policy_sha == row.payload["risk_assessment"]["policy_sha"]


def test_episodic_store_records_vetoed_decisions_open_question_1(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """Test 13: VETOED rows are stored (07-RESEARCH.md Open Question 1
    recommendation -- vetoes are the richest learning signal).
    """
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    state = _post_debate_state(
        signal_direction=None,  # veto -> signal absent
        risk_status="VETOED",
    )
    state["signal"] = None

    result = _run_store(state, deps)
    assert "episodic_stored_id" in result

    row = memory_db_session.query(EpisodicMemory).filter_by(id=result["episodic_stored_id"]).one()
    assert row.payload["risk_assessment"]["status"] == "VETOED"
    assert row.signal_direction is None  # not blocked, just absent


def test_episodic_store_short_circuits_on_upstream_error(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """Test 14: state['error'] -> {} and NO DB write."""
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    baseline = memory_db_session.query(EpisodicMemory).count()

    state = _post_debate_state()
    state["error"] = "upstream bail"
    result = _run_store(state, deps)

    assert result == {}
    assert memory_db_session.query(EpisodicMemory).count() == baseline
