"""Tests for the ingest_outcome CLI function (Plan 07-04 Task 3).

End-to-end offline self-critique loop:
    1. Validate ticker regex (T-07-40 path-traversal guard).
    2. Append outcome row to ``episodic_memory`` (append-only).
    3. Compute new confidence via :func:`compute_new_confidence`
       (deterministic, Pattern 2).
    4. Ask :attr:`self_critique_agent` for a rationale (advisory only).
    5. Apply via :func:`write_belief` (MEM-03 human-edit guard at the
       writer -- verified independently in 07-02).

The MEM-03 x MEM-04 cross-requirement test
(``test_ingest_outcome_respects_human_edited_belief``) proves that a
human-edited belief SURVIVES an outcome ingest: the outcome row lands
in episodic memory (operational fact), but ``confidence`` is NOT
overwritten and ``critique_history`` is still audited.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pytest
from pydantic_ai.models.test import TestModel
from sqlalchemy.orm import Session

from ai_hedge_fund.agents.self_critique import self_critique_agent
from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.memory import load_belief
from ai_hedge_fund.scripts.ingest_outcome import ingest_outcome

STUB_RATIONALE = "stubbed self-critique rationale for tests"


def _seed_analysis(
    session: Session,
    ticker: str,
    as_of: date,
    signal_direction: str = "long",
    policy_sha: str = "abcd" * 16,
) -> EpisodicMemory:
    """Seed a single record_type='analysis' row and return it."""
    row = EpisodicMemory(
        ticker=ticker,
        sector="Technology",
        record_type="analysis",
        signal_direction=signal_direction,
        confidence=72,
        policy_sha=policy_sha,
        as_of_date=datetime(as_of.year, as_of.month, as_of.day, tzinfo=UTC),
        payload={
            "schema_version": 1,
            "thesis": {"confidence": 72, "direction": signal_direction},
        },
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# ---------- Test 1: happy path (agreed outcome, human_edited=false) ----------


def test_ingest_outcome_happy_path(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
) -> None:
    analysis = _seed_analysis(memory_db_session, "AAPL", date(2026, 1, 10))

    with self_critique_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = asyncio.run(
            ingest_outcome(
                session=memory_db_session,
                beliefs_dir=beliefs_tmp_dir,
                ticker="AAPL",
                outcome_pct=+4.2,
                as_of_date=date(2026, 4, 20),
            )
        )

    # Outcome row appended to episodic_memory.
    outcome_rows = (
        memory_db_session.query(EpisodicMemory)
        .filter_by(ticker="AAPL", record_type="outcome")
        .all()
    )
    assert len(outcome_rows) == 1
    outcome_row = outcome_rows[0]
    assert outcome_row.outcome_pct == pytest.approx(4.2)
    assert outcome_row.linked_analysis_id == analysis.id
    assert outcome_row.signal_direction == "long"
    assert outcome_row.policy_sha == analysis.policy_sha
    assert outcome_row.sector == "Technology"

    # Belief confidence updated: old=72, +4.2 long agreed -> +min(0.3*4.2*10,
    # 10) = +10 (capped) -> 82.
    fresh_belief, _ = load_belief(beliefs_tmp_dir / "tickers" / "AAPL.yaml")
    assert fresh_belief.confidence == 82

    # critique_history grew by one with source='self_critique'.
    assert len(fresh_belief.critique_history) == 3  # fixture had 2 entries.
    new_event = fresh_belief.critique_history[-1]
    assert new_event.rationale == STUB_RATIONALE
    assert new_event.source == "self_critique"
    assert new_event.outcome_pct == pytest.approx(4.2)
    assert new_event.old_confidence == 72
    assert new_event.new_confidence == 82

    # Return dict shape.
    assert "confidence" in result["applied"]
    assert "critique_history" in result["applied"]
    assert result["skipped"] == {}
    assert result["new_confidence"] == 82


# ---------- Test 2: MEM-03 x MEM-04 cross-requirement ----------


def test_ingest_outcome_respects_human_edited_belief(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
) -> None:
    """Human-edited belief survives an outcome ingest.

    Outcome row IS appended (operational fact). confidence is NOT
    overwritten (human_edited=true). critique_history IS updated so
    operators can audit that the machine tried.
    """
    # Replace the plain AAPL.yaml fixture with the human-edited variant.
    shutil.copy2(
        beliefs_tmp_dir / "tickers" / "AAPL_human.yaml",
        beliefs_tmp_dir / "tickers" / "AAPL.yaml",
    )
    _seed_analysis(memory_db_session, "AAPL", date(2026, 1, 10))

    with self_critique_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = asyncio.run(
            ingest_outcome(
                session=memory_db_session,
                beliefs_dir=beliefs_tmp_dir,
                ticker="AAPL",
                outcome_pct=+4.2,
                as_of_date=date(2026, 4, 20),
            )
        )

    # Outcome row STILL appended -- operational fact unchanged.
    assert (
        memory_db_session.query(EpisodicMemory)
        .filter_by(ticker="AAPL", record_type="outcome")
        .count()
        == 1
    )

    # Belief's confidence NOT changed -- human pinned it to 20.
    fresh_belief, _ = load_belief(beliefs_tmp_dir / "tickers" / "AAPL.yaml")
    assert fresh_belief.confidence == 20

    # Writer audit: confidence was skipped with the human-edited reason.
    assert "confidence" in result["skipped"]
    assert result["skipped"]["confidence"] == "human_edited_global_flag_set"

    # critique_history IS updated -- audit trail matters.
    assert "critique_history" in result["applied"]
    assert fresh_belief.critique_history[-1].rationale == STUB_RATIONALE
    assert fresh_belief.critique_history[-1].source == "self_critique"


# ---------- Test 3: path-traversal guard ----------


def test_ingest_outcome_path_traversal_rejected(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
) -> None:
    """Invalid tickers raise ValueError BEFORE any DB write."""
    with pytest.raises(ValueError):
        asyncio.run(
            ingest_outcome(
                session=memory_db_session,
                beliefs_dir=beliefs_tmp_dir,
                ticker="../../etc/passwd",
                outcome_pct=1.0,
                as_of_date=date(2026, 4, 20),
            )
        )

    # No partial state: no outcome row was inserted.
    assert memory_db_session.query(EpisodicMemory).count() == 0


# ---------- Test 4: bootstrap case (no belief file yet) ----------


def test_ingest_outcome_missing_belief_file(
    memory_db_session: Session,
    tmp_path: Path,
) -> None:
    """No belief file -> FileNotFoundError, but outcome row IS still appended."""
    beliefs_dir = tmp_path / "beliefs"
    (beliefs_dir / "tickers").mkdir(parents=True)
    _seed_analysis(memory_db_session, "AAPL", date(2026, 1, 10))

    with self_critique_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        with pytest.raises(FileNotFoundError, match="AAPL"):
            asyncio.run(
                ingest_outcome(
                    session=memory_db_session,
                    beliefs_dir=beliefs_dir,
                    ticker="AAPL",
                    outcome_pct=+4.2,
                    as_of_date=date(2026, 4, 20),
                )
            )

    # Outcome row WAS appended before the FileNotFoundError propagated.
    assert (
        memory_db_session.query(EpisodicMemory)
        .filter_by(ticker="AAPL", record_type="outcome")
        .count()
        == 1
    )


# ---------- Test 5: no prior analysis row ----------


def test_ingest_outcome_without_prior_analysis(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
) -> None:
    """With no linked analysis: outcome row is appended with null linkage,
    and compute_new_confidence treats the signal as 'neutral'."""
    # NO analysis row seeded.
    with self_critique_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = asyncio.run(
            ingest_outcome(
                session=memory_db_session,
                beliefs_dir=beliefs_tmp_dir,
                ticker="AAPL",
                outcome_pct=+4.2,
                as_of_date=date(2026, 4, 20),
            )
        )

    # Outcome row with no linked analysis.
    outcome_rows = (
        memory_db_session.query(EpisodicMemory)
        .filter_by(ticker="AAPL", record_type="outcome")
        .all()
    )
    assert len(outcome_rows) == 1
    outcome_row = outcome_rows[0]
    assert outcome_row.linked_analysis_id is None
    assert outcome_row.signal_direction is None

    # Belief updated with neutral-signal math: old=72 - min(0.3*4.2*10, 10)
    # = 72 - 10 (capped) = 62.
    fresh_belief, _ = load_belief(beliefs_tmp_dir / "tickers" / "AAPL.yaml")
    assert fresh_belief.confidence == 62
    assert result["new_confidence"] == 62
