"""Plan 08-03 Task 1: ReviewDeps + output_node + review_store_node + route_before_review.

Covers:
    Tests 1-5:  ReviewDeps construction (XOR policy/policy_path; frozen).
    Tests 6-10: output_node (assembles FinalSignalOutput; short-circuits;
                stamps review_policy_sha from deps).
    Tests 18-25: review_store_node (appends record_type='review';
                 NOT_REQUIRED + APPROVED paths; T-08-05 append-only;
                 SHA columns + structlog event).
    Tests 26-31: route_before_review (fail-closed router).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.graph.nodes import (
    output_node,
    review_store_node,
    route_before_review,
)
from ai_hedge_fund.graph.review_deps import ReviewDeps
from ai_hedge_fund.review.policy import ReviewPolicy, compute_review_policy_sha


# ============================================================
# ReviewDeps tests (Tests 1-5)
# ============================================================


def test_review_deps_with_policy_ok(portfolio_db_session: Session) -> None:
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    assert deps.policy is not None


def test_review_deps_with_policy_path_ok(
    portfolio_db_session: Session, tmp_path: Path
) -> None:
    p = tmp_path / "rp.yaml"
    p.write_text("conviction_threshold: 70\n")
    deps = ReviewDeps(db_session=portfolio_db_session, policy_path=p)
    assert deps.policy_path == p


def test_review_deps_both_raises(
    portfolio_db_session: Session, tmp_path: Path
) -> None:
    p = tmp_path / "rp.yaml"
    p.write_text("conviction_threshold: 70\n")
    with pytest.raises(ValueError, match="exactly one"):
        ReviewDeps(
            db_session=portfolio_db_session,
            policy=ReviewPolicy(),
            policy_path=p,
        )


def test_review_deps_neither_raises(portfolio_db_session: Session) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ReviewDeps(db_session=portfolio_db_session)


def test_review_deps_is_frozen(portfolio_db_session: Session) -> None:
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    with pytest.raises(Exception):
        deps.db_session = None  # type: ignore[misc]


# ============================================================
# output_node tests (Tests 6-10)
# ============================================================


def _base_state_for_output() -> dict:
    return {
        "ticker": "AAPL",
        "as_of_date": "2026-04-20",
        "signal": {"direction": "long", "thesis_summary": "Bullish."},
        "thesis": {"confidence": 85, "bull_case": "b", "bear_case": "c"},
        "risk_assessment": {
            "status": "APPROVED",
            "policy_sha": "a" * 64,
            "observed": 4.0,
            "limit": 8.0,
        },
        "episodic_stored_id": 7,
    }


def test_output_assembles_final_signal(portfolio_db_session: Session) -> None:
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    result = asyncio.run(output_node(_base_state_for_output(), deps))
    fs = result["final_signal"]
    assert fs["ticker"] == "AAPL"
    assert fs["direction"] == "long"
    assert fs["conviction"] == 85
    assert fs["thesis_link"] == "episodic://7"
    assert fs["policy_sha"] == "a" * 64
    assert fs["review_policy_sha"] == compute_review_policy_sha(ReviewPolicy())
    assert fs["review_status"] == "NOT_REQUIRED"


def test_output_short_circuits_on_error(portfolio_db_session: Session) -> None:
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    state = _base_state_for_output()
    state["error"] = "x"
    assert asyncio.run(output_node(state, deps)) == {}


def test_output_error_on_missing_signal(portfolio_db_session: Session) -> None:
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    state = _base_state_for_output()
    del state["signal"]
    res = asyncio.run(output_node(state, deps))
    assert "error" in res and "No signal" in res["error"]


def test_output_error_on_missing_episodic_id(portfolio_db_session: Session) -> None:
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    state = _base_state_for_output()
    del state["episodic_stored_id"]
    res = asyncio.run(output_node(state, deps))
    assert "error" in res and "episodic_stored_id" in res["error"]


def test_output_stamps_review_policy_sha(portfolio_db_session: Session) -> None:
    policy = ReviewPolicy(conviction_threshold=80)
    deps = ReviewDeps(db_session=portfolio_db_session, policy=policy)
    res = asyncio.run(output_node(_base_state_for_output(), deps))
    assert res["final_signal"]["review_policy_sha"] == compute_review_policy_sha(policy)


# ============================================================
# review_store_node tests (Tests 18-25)
# ============================================================


def _seed_analysis(
    session: Session, *, ticker: str = "AAPL", policy_sha: str = "a" * 64
) -> int:
    row = EpisodicMemory(
        ticker=ticker,
        sector="Technology",
        record_type="analysis",
        signal_direction="long",
        confidence=85,
        outcome_pct=None,
        linked_analysis_id=None,
        policy_sha=policy_sha,
        as_of_date=date(2026, 4, 20),
        payload={"thesis": {"bull_case": "b"}, "signal": {"direction": "long"}},
    )
    session.add(row)
    session.commit()
    return row.id


def _review_state(analysis_id: int, *, decision: dict | None = None) -> dict:
    return {
        "ticker": "AAPL",
        "as_of_date": "2026-04-20",
        "candidate_metadata": {"sector": "Technology"},
        "final_signal": {
            "direction": "long",
            "conviction": 85,
            "review_policy_sha": "b" * 64,
        },
        "risk_assessment": {"status": "APPROVED", "policy_sha": "a" * 64},
        "episodic_stored_id": analysis_id,
        "review_decision": decision,
    }


def test_review_store_appends_review_row(portfolio_db_session: Session) -> None:
    aid = _seed_analysis(portfolio_db_session)
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    res = asyncio.run(review_store_node(_review_state(aid), deps))
    assert res["review_stored_id"] != aid
    rows = (
        portfolio_db_session.query(EpisodicMemory)
        .filter_by(record_type="review")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].linked_analysis_id == aid


def test_review_store_not_required_path(portfolio_db_session: Session) -> None:
    aid = _seed_analysis(portfolio_db_session)
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    asyncio.run(review_store_node(_review_state(aid, decision=None), deps))
    row = (
        portfolio_db_session.query(EpisodicMemory)
        .filter_by(record_type="review")
        .one()
    )
    assert row.payload["review_status"] == "NOT_REQUIRED"


def test_review_store_approved_path(portfolio_db_session: Session) -> None:
    aid = _seed_analysis(portfolio_db_session)
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    decision = {
        "status": "APPROVED",
        "reviewer_id": "maxzou",
        "reviewer_note": "ok",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_policy_sha": "b" * 64,
    }
    asyncio.run(review_store_node(_review_state(aid, decision=decision), deps))
    row = (
        portfolio_db_session.query(EpisodicMemory)
        .filter_by(record_type="review")
        .one()
    )
    assert row.payload["review_status"] == "APPROVED"
    assert row.payload["review_decision"]["status"] == "APPROVED"


def test_analysis_row_unchanged_after_review_store(
    portfolio_db_session: Session,
) -> None:
    """T-08-05 append-only: analysis row MUST be byte-identical after review."""
    aid = _seed_analysis(portfolio_db_session)
    before = portfolio_db_session.get(EpisodicMemory, aid)
    before_snapshot = {
        "payload": dict(before.payload),
        "signal_direction": before.signal_direction,
        "confidence": before.confidence,
        "record_type": before.record_type,
    }

    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    asyncio.run(review_store_node(_review_state(aid), deps))

    after = portfolio_db_session.get(EpisodicMemory, aid)
    assert after.payload == before_snapshot["payload"]
    assert after.signal_direction == before_snapshot["signal_direction"]
    assert after.confidence == before_snapshot["confidence"]
    assert after.record_type == before_snapshot["record_type"]


def test_review_row_policy_sha_from_risk(portfolio_db_session: Session) -> None:
    aid = _seed_analysis(portfolio_db_session, policy_sha="c" * 64)
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    state = _review_state(aid)
    state["risk_assessment"]["policy_sha"] = "c" * 64
    asyncio.run(review_store_node(state, deps))
    row = (
        portfolio_db_session.query(EpisodicMemory)
        .filter_by(record_type="review")
        .one()
    )
    assert row.policy_sha == "c" * 64


def test_review_row_review_policy_sha_in_payload(
    portfolio_db_session: Session,
) -> None:
    aid = _seed_analysis(portfolio_db_session)
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    decision = {
        "status": "APPROVED",
        "reviewer_id": "maxzou",
        "reviewer_note": "ok",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_policy_sha": "e" * 64,
    }
    asyncio.run(review_store_node(_review_state(aid, decision=decision), deps))
    row = (
        portfolio_db_session.query(EpisodicMemory)
        .filter_by(record_type="review")
        .one()
    )
    assert row.payload["review_policy_sha"] == "e" * 64


def test_review_store_structlog_event(portfolio_db_session: Session) -> None:
    from structlog.testing import capture_logs

    aid = _seed_analysis(portfolio_db_session)
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    with capture_logs() as events:
        asyncio.run(review_store_node(_review_state(aid), deps))
    assert any(e.get("event") == "review_store_complete" for e in events)


def test_review_store_short_circuits_on_error(portfolio_db_session: Session) -> None:
    aid = _seed_analysis(portfolio_db_session)
    deps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    state = _review_state(aid)
    state["error"] = "x"
    assert asyncio.run(review_store_node(state, deps)) == {}


# ============================================================
# route_before_review tests (Tests 26-31)
# ============================================================


def test_route_above_threshold_goes_to_review() -> None:
    state = {"final_signal": {"conviction": 85}, "_review_threshold": 70}
    assert route_before_review(state) == "human_review"


def test_route_below_threshold_skips_review() -> None:
    state = {"final_signal": {"conviction": 50}, "_review_threshold": 70}
    assert route_before_review(state) == "review_store"


def test_route_at_threshold_is_review_gte() -> None:
    state = {"final_signal": {"conviction": 70}, "_review_threshold": 70}
    assert route_before_review(state) == "human_review"


def test_route_missing_final_signal_fails_closed() -> None:
    state = {"_review_threshold": 70}
    assert route_before_review(state) == "human_review"


def test_route_missing_threshold_fails_closed() -> None:
    state = {"final_signal": {"conviction": 85}}
    assert route_before_review(state) == "human_review"


def test_route_return_type() -> None:
    state = {"final_signal": {"conviction": 50}, "_review_threshold": 70}
    result = route_before_review(state)
    assert result in {"human_review", "review_store"}
