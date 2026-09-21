"""Plan 08-02 Task 2: reconstruct_audit_trail + audit_reconstruct CLI tests.

Covers SIG-04 read-side (Pitfall G: reconstruction substrate). Ten tests:

    1. Happy path with review row
    2. Analysis only (no review)
    3. Not-found episodic_id raises ValueError
    4. Wrong record_type (outcome) raises ValueError
    5. Two review rows -> returns the latest (highest id)
    6. analysis.policy_sha preserved verbatim
    7. review_policy_sha from payload preserved
    8. thread_id hint format
    9. CLI missing --episodic-id exits non-zero
    10. CLI prints valid JSON containing analysis_row
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.scripts.audit_reconstruct import (
    _main,
    reconstruct_audit_trail,
)


def _insert_analysis(
    session: Session,
    *,
    ticker: str = "AAPL",
    as_of: str = "2026-04-20",
    policy_sha: str = "a" * 64,
    payload: dict | None = None,
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
        as_of_date=date.fromisoformat(as_of),
        payload=payload
        or {
            "thesis": {"bull_case": "bullish"},
            "signal": {"direction": "long"},
        },
    )
    session.add(row)
    session.flush()
    return row.id


def _insert_review(
    session: Session,
    *,
    analysis_id: int,
    status: str = "APPROVED",
    review_policy_sha: str = "b" * 64,
    policy_sha: str = "a" * 64,
) -> int:
    row = EpisodicMemory(
        ticker="AAPL",
        sector="Technology",
        record_type="review",
        signal_direction="long",
        confidence=85,
        outcome_pct=None,
        linked_analysis_id=analysis_id,
        policy_sha=policy_sha,
        as_of_date=date(2026, 4, 20),
        payload={
            "review_status": status,
            "review_policy_sha": review_policy_sha,
            "review_decision": {
                "status": status,
                "reviewer_id": "maxzou",
                "reviewer_note": "ok",
                "review_policy_sha": review_policy_sha,
            },
        },
    )
    session.add(row)
    session.flush()
    return row.id


def _insert_outcome(
    session: Session,
    *,
    analysis_id: int,
    outcome_pct: float = 4.0,
) -> int:
    row = EpisodicMemory(
        ticker="AAPL",
        sector="Technology",
        record_type="outcome",
        signal_direction="long",
        confidence=None,
        outcome_pct=outcome_pct,
        linked_analysis_id=analysis_id,
        policy_sha="a" * 64,
        as_of_date=date(2026, 4, 25),
        payload={"outcome_pct": outcome_pct},
    )
    session.add(row)
    session.flush()
    return row.id


def test_happy_path_with_review(portfolio_db_session: Session) -> None:
    """Test 1: analysis + linked review -> both in result."""
    aid = _insert_analysis(portfolio_db_session)
    _insert_review(portfolio_db_session, analysis_id=aid)
    portfolio_db_session.commit()

    result = reconstruct_audit_trail(portfolio_db_session, aid)
    assert result["analysis_row"]["id"] == aid
    assert result["analysis_row"]["ticker"] == "AAPL"
    assert result["analysis_row"]["policy_sha"] == "a" * 64
    assert result["review_row"] is not None
    assert result["review_row"]["status"] == "APPROVED"
    assert result["review_row"]["review_policy_sha"] == "b" * 64
    assert "thread_id" in result["langfuse_trace_hint"]


def test_analysis_without_review(portfolio_db_session: Session) -> None:
    """Test 2: analysis only -> review_row is None."""
    aid = _insert_analysis(portfolio_db_session)
    portfolio_db_session.commit()

    result = reconstruct_audit_trail(portfolio_db_session, aid)
    assert result["analysis_row"]["id"] == aid
    assert result["review_row"] is None


def test_not_found_raises(portfolio_db_session: Session) -> None:
    """Test 3: missing id -> ValueError('No analysis row ...')."""
    with pytest.raises(ValueError, match="No analysis row"):
        reconstruct_audit_trail(portfolio_db_session, 999999)


def test_wrong_record_type_raises(portfolio_db_session: Session) -> None:
    """Test 4: id pointing at an outcome row -> ValueError."""
    aid = _insert_analysis(portfolio_db_session)
    oid = _insert_outcome(portfolio_db_session, analysis_id=aid)
    portfolio_db_session.commit()

    with pytest.raises(ValueError, match="No analysis row"):
        reconstruct_audit_trail(portfolio_db_session, oid)


def test_latest_review_when_multiple(portfolio_db_session: Session) -> None:
    """Test 5: two reviews for one analysis -> returns the higher-id (latest)."""
    aid = _insert_analysis(portfolio_db_session)
    r1 = _insert_review(
        portfolio_db_session,
        analysis_id=aid,
        status="APPROVED",
        review_policy_sha="c" * 64,
    )
    r2 = _insert_review(
        portfolio_db_session,
        analysis_id=aid,
        status="REJECTED",
        review_policy_sha="d" * 64,
    )
    portfolio_db_session.commit()
    assert r2 > r1  # sanity: second insert has higher id

    result = reconstruct_audit_trail(portfolio_db_session, aid)
    assert result["review_row"]["id"] == r2
    assert result["review_row"]["status"] == "REJECTED"
    assert result["review_row"]["review_policy_sha"] == "d" * 64


def test_policy_sha_preserved(portfolio_db_session: Session) -> None:
    """Test 6: analysis.policy_sha survives round-trip verbatim."""
    aid = _insert_analysis(portfolio_db_session, policy_sha="f" * 64)
    portfolio_db_session.commit()

    result = reconstruct_audit_trail(portfolio_db_session, aid)
    assert result["analysis_row"]["policy_sha"] == "f" * 64


def test_review_policy_sha_preserved(portfolio_db_session: Session) -> None:
    """Test 7: review.payload['review_policy_sha'] surfaces at the top level."""
    aid = _insert_analysis(portfolio_db_session)
    _insert_review(portfolio_db_session, analysis_id=aid, review_policy_sha="e" * 64)
    portfolio_db_session.commit()

    result = reconstruct_audit_trail(portfolio_db_session, aid)
    assert result["review_row"]["review_policy_sha"] == "e" * 64


def test_thread_id_hint_format(portfolio_db_session: Session) -> None:
    """Test 8: thread_id contains ticker + as_of_date (Langfuse search hint)."""
    aid = _insert_analysis(portfolio_db_session, ticker="MSFT", as_of="2026-03-15")
    portfolio_db_session.commit()

    result = reconstruct_audit_trail(portfolio_db_session, aid)
    tid = result["langfuse_trace_hint"]["thread_id"]
    assert "MSFT" in tid
    assert "2026-03-15" in tid


def test_cli_missing_arg_exits_nonzero() -> None:
    """Test 9: argparse rejects missing --episodic-id."""
    with pytest.raises(SystemExit) as excinfo:
        _main([])
    assert excinfo.value.code != 0


def test_cli_prints_valid_json(
    portfolio_db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """Test 10: _main prints JSON with analysis_row (session monkeypatched)."""
    aid = _insert_analysis(portfolio_db_session)
    portfolio_db_session.commit()

    # Monkeypatch engine + factory so CLI uses the shared test session.
    def _fake_engine(_url: str) -> object:
        return object()

    def _fake_factory(_engine: object) -> object:
        return lambda: portfolio_db_session

    monkeypatch.setattr("ai_hedge_fund.db.session.get_engine", _fake_engine)
    monkeypatch.setattr("ai_hedge_fund.db.session.get_session_factory", _fake_factory)

    # Prevent _main's finally: session.close() from closing the shared session.
    original_close = portfolio_db_session.close
    portfolio_db_session.close = lambda: None  # type: ignore[method-assign]
    try:
        rc = _main(["--episodic-id", str(aid), "--database-url", "sqlite:///:memory:"])
    finally:
        portfolio_db_session.close = original_close  # type: ignore[method-assign]

    assert rc == 0
    out = capsys.readouterr().out
    # Structlog may emit a human-readable log line on stdout before the JSON.
    # Strip everything before the first ``{`` so we parse only the CLI payload.
    json_start = out.find("{")
    assert json_start != -1, f"No JSON object in CLI output: {out!r}"
    parsed = json.loads(out[json_start:])
    assert parsed["analysis_row"]["id"] == aid
