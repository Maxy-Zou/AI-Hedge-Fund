"""Phase 9 -- CSV seeders (test-fixture infrastructure for PT-05 and Phase 10+)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import PaperFill, PaperTrade
from ai_hedge_fund.paper import AmbiguousSignal, DuplicateSubmission, SignalNotFound, TradeNotFound
from ai_hedge_fund.paper.seed import seed_paper_fills_from_csv, seed_paper_trades_from_csv
from tests.paper.conftest import SHA

TRADE_HEADER = (
    "signal_ticker,signal_as_of_date,attempt_no,ticker,side,order_type,quantity,"
    "limit_price_cents,submit_status,broker_order_id,risk_status_at_submit,"
    "policy_sha,review_policy_sha,as_of_date\n"
)
FILL_HEADER = "broker_order_id,broker_fill_id,filled_qty,fill_price_cents,filled_at,as_of_date\n"


def _trade_csv(tmp_path: Path, *rows: str) -> Path:
    p = tmp_path / "trades.csv"
    p.write_text(TRADE_HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
    return p


def _fill_csv(tmp_path: Path, *rows: str) -> Path:
    p = tmp_path / "fills.csv"
    p.write_text(FILL_HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
    return p


# --------------------------------------------------------------------------- happy path


def test_fixture_counts(
    db_session: Session, seeded_signals: int, seeded_ledger: tuple[int, int]
) -> None:
    assert seeded_signals == 9
    assert seeded_ledger == (6, 5)
    assert db_session.query(PaperTrade).count() == 6
    assert db_session.query(PaperFill).count() == 5


def test_seeded_trades_have_expected_shape(
    db_session: Session, seeded_ledger: tuple[int, int]
) -> None:
    by_broker = {t.broker_order_id: t for t in db_session.query(PaperTrade).all()}
    assert by_broker["ord-aapl-2"].order_type == "limit"
    assert by_broker["ord-aapl-2"].limit_price_cents == 1_800_000
    rejected = db_session.query(PaperTrade).filter_by(submit_status="rejected").one()
    assert rejected.broker_order_id is None and rejected.attempt_no == 1
    retry = by_broker["ord-msft-2"]
    assert retry.attempt_no == 2 and retry.signal_id == rejected.signal_id
    vetoed = db_session.query(PaperTrade).filter_by(submit_status="refused_veto").one()
    assert vetoed.risk_status_at_submit == "VETOED" and vetoed.broker_order_id is None


def test_seeded_fills_link_to_trades(db_session: Session, seeded_ledger: tuple[int, int]) -> None:
    aapl1 = db_session.query(PaperTrade).filter_by(broker_order_id="ord-aapl-1").one()
    fills = db_session.query(PaperFill).filter_by(trade_id=aapl1.id).all()
    assert sorted(f.filled_qty for f in fills) == [4, 6]  # two partial fills


def test_review_row_with_same_ticker_and_date_is_not_a_signal(
    db_session: Session, seeded_ledger: tuple[int, int]
) -> None:
    """AAPL 2026-04-10 has an analysis AND a review row; resolver must pick only the analysis."""
    t = db_session.query(PaperTrade).filter_by(broker_order_id="ord-aapl-2").one()
    from ai_hedge_fund.db.models import EpisodicMemory

    assert db_session.get(EpisodicMemory, t.signal_id).record_type == "analysis"


# --------------------------------------------------------------------------- resolution errors


def test_unknown_signal_raises(db_session: Session, seeded_signals: int, tmp_path: Path) -> None:
    csv = _trade_csv(
        tmp_path, f"ZZZZ,2026-04-01,1,ZZZZ,buy,market,1,,rejected,,APPROVED,{SHA},{SHA},2026-04-01"
    )
    with pytest.raises(SignalNotFound):
        seed_paper_trades_from_csv(db_session, csv)


def test_only_review_row_raises_not_found(
    db_session: Session, seeded_signals: int, tmp_path: Path
) -> None:
    csv = _trade_csv(
        tmp_path,
        f"ONLYREV,2026-04-16,1,ONLYREV,buy,market,1,,rejected,,APPROVED,{SHA},{SHA},2026-04-16",
    )
    with pytest.raises(SignalNotFound):
        seed_paper_trades_from_csv(db_session, csv)


def test_duplicate_signal_rows_raise_ambiguous(
    db_session: Session, seeded_signals: int, tmp_path: Path
) -> None:
    """09-PREMORTEM #16: episodic allows duplicates; the seeder must not silently pick one."""
    csv = _trade_csv(
        tmp_path, f"DUPX,2026-04-15,1,DUPX,buy,market,1,,rejected,,APPROVED,{SHA},{SHA},2026-04-15"
    )
    with pytest.raises(AmbiguousSignal):
        seed_paper_trades_from_csv(db_session, csv)


def test_reseeding_same_trades_raises_duplicate(
    db_session: Session, seeded_ledger: tuple[int, int], paper_trades_csv_path: Path
) -> None:
    """Seeders go through insert_paper_trade, so they inherit its idempotency error."""
    with pytest.raises(DuplicateSubmission):
        seed_paper_trades_from_csv(db_session, paper_trades_csv_path)


def test_fill_for_unknown_broker_order_raises(
    db_session: Session, seeded_ledger: tuple[int, int], tmp_path: Path
) -> None:
    csv = _fill_csv(tmp_path, "ord-nope,fill-x,1,100,2026-04-01T14:00:00+00:00,2026-04-01")
    with pytest.raises(TradeNotFound):
        seed_paper_fills_from_csv(db_session, csv)


def test_empty_csv_seeds_nothing(db_session: Session, seeded_signals: int, tmp_path: Path) -> None:
    assert seed_paper_trades_from_csv(db_session, _trade_csv(tmp_path)) == 0
