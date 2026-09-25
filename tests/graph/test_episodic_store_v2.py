"""Phase 11 T2 -- episodic_store_node persists attribution inputs (11-SPEC s2, D2 + A2).

Fixtures come from ``tests/memory/conftest.py`` via the ``tests/graph/conftest.py`` shim.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.graph.memory_deps import MemoryDeps
from ai_hedge_fund.graph.nodes import episodic_store_node
from ai_hedge_fund.mtm.policy import MtmPolicy, compute_mtm_policy_sha, load_mtm_policy


def _state(**extra: object) -> dict:
    return {
        "ticker": "AAPL",
        "as_of_date": "2026-04-20",
        "candidate_metadata": {"sector": "Technology", "instrument_type": "equity"},
        "thesis": {"ticker": "AAPL", "confidence": 72, "bull_case": [], "bear_case": []},
        "signal": {"ticker": "AAPL", "direction": "long", "conviction": 72},
        "risk_assessment": {"status": "APPROVED", "policy_sha": "a" * 64},
        "analyst_reports": [
            {
                "analyst": "fundamental",
                "analysis": {"bull_factors": ["x", "y"], "bear_factors": ["z"]},
            },
            {"analyst": "sentiment", "analysis": {"composite_score": -0.5}},
            {"analyst": "technical", "analysis": {}, "error": "no prices"},
        ],
        "debate_synthesis": {
            "pre_debate_confidence": 60,
            "post_debate_confidence": 72,
            "quality_score": 81,
            "synthesis_notes": "moved up",
        },
        **extra,
    }


def _store(state: dict, deps: MemoryDeps) -> EpisodicMemory:
    out = asyncio.run(episodic_store_node(state, deps))
    return deps.db_session.query(EpisodicMemory).filter_by(id=out["episodic_stored_id"]).one()


def test_memory_deps_defaults_to_shipped_mtm_policy(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    assert deps.mtm_policy == load_mtm_policy()


def test_stances_persisted(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    """11-PREMORTEM #23: stances are frozen at write time, not re-derived later."""
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    row = _store(_state(), deps)
    assert row.payload["schema_version"] == 2
    assert row.payload["analyst_stances"] == {
        "fundamental": "bull",
        "sentiment": "bear",
        "technical": "absent",
    }
    assert row.payload["mtm_policy_sha"] == compute_mtm_policy_sha(deps.mtm_policy)


def test_debate_pre_confidence_from_state(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """11-PREMORTEM #25: pre comes from debate_synthesis, not the (already revised) thesis."""
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    row = _store(_state(), deps)
    assert row.payload["debate"] == {
        "pre_debate_confidence": 60,
        "post_debate_confidence": 72,
        "quality_score": 81,
    }
    assert row.payload["thesis"]["confidence"] == 72  # revised value, untouched


def test_no_debate_stores_none(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    """11-PREMORTEM #26: a Phase-4-style run (no debate, no analysts) still stores."""
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    state = _state()
    del state["debate_synthesis"]
    del state["analyst_reports"]
    row = _store(state, deps)
    assert row.payload["debate"] is None
    assert set(row.payload["analyst_stances"].values()) == {"absent"}


def test_existing_payload_fields_unchanged(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """D2 is additive: every v1 key is still written with the same value."""
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    state = _state()
    row = _store(state, deps)
    assert row.payload["thesis"] == state["thesis"]
    assert row.payload["signal"] == state["signal"]
    assert row.payload["risk_assessment"] == state["risk_assessment"]
    assert row.payload["episodic_hits_count"] == 0
    assert row.payload["beliefs_consulted_count"] == 0


def test_injected_policy_is_used(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    """A stricter threshold changes the stance and the recorded SHA together."""
    base = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    strict: MtmPolicy = base.mtm_policy.model_copy(update={"sentiment_threshold": 0.6})
    deps = replace(base, mtm_policy=strict)
    row = _store(_state(), deps)
    assert row.payload["analyst_stances"]["sentiment"] == "neutral"
    assert row.payload["mtm_policy_sha"] == compute_mtm_policy_sha(strict)
