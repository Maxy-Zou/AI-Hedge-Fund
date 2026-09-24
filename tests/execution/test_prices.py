"""Phase 10 T4 -- as-of price lookup (D5; determinism + temporal, 09-PREMORTEM #3/#4)."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import DailyPrice
from ai_hedge_fund.execution.errors import NoPriceAvailable
from ai_hedge_fund.execution.prices import latest_adj_close_cents


def _price(db_session: Session, ticker: str, d: str, adj: int) -> None:
    db_session.add(
        DailyPrice(
            ticker=ticker,
            trade_date=date.fromisoformat(d),
            open_cents=adj,
            high_cents=adj,
            low_cents=adj,
            close_cents=adj,
            adj_close_cents=adj,
            volume=1_000,
            source="test",
            as_of_date=datetime.fromisoformat(d + "T00:00:00+00:00"),
        )
    )
    db_session.commit()


def test_returns_latest_on_or_before_as_of(db_session: Session) -> None:
    _price(db_session, "AAPL", "2026-04-10", 18_000_00)
    _price(db_session, "AAPL", "2026-04-17", 18_500_00)
    _price(db_session, "AAPL", "2026-04-20", 19_000_00)
    assert latest_adj_close_cents(db_session, "AAPL", "2026-04-18") == 18_500_00


def test_boundary_row_on_as_of_is_included(db_session: Session) -> None:
    _price(db_session, "AAPL", "2026-04-18", 18_800_00)
    assert latest_adj_close_cents(db_session, "AAPL", "2026-04-18") == 18_800_00


def test_future_rows_excluded(db_session: Session) -> None:
    """09-PREMORTEM #4: a later close must not be used to size an as-of signal."""
    _price(db_session, "AAPL", "2026-04-17", 18_500_00)
    _price(db_session, "AAPL", "2099-01-01", 99_999_00)
    assert latest_adj_close_cents(db_session, "AAPL", "2026-04-18") == 18_500_00


def test_no_price_raises(db_session: Session) -> None:
    _price(db_session, "AAPL", "2026-04-20", 19_000_00)  # only a future row
    with pytest.raises(NoPriceAvailable):
        latest_adj_close_cents(db_session, "AAPL", "2026-04-18")


def test_unknown_ticker_raises(db_session: Session) -> None:
    with pytest.raises(NoPriceAvailable):
        latest_adj_close_cents(db_session, "NOPE", "2026-04-18")


def test_string_date_and_datetime_equivalent(db_session: Session) -> None:
    _price(db_session, "AAPL", "2026-04-17", 18_500_00)
    a = latest_adj_close_cents(db_session, "AAPL", "2026-04-18")
    b = latest_adj_close_cents(db_session, "AAPL", date(2026, 4, 18))
    c = latest_adj_close_cents(db_session, "AAPL", datetime(2026, 4, 18, 15, 0))
    assert a == b == c
