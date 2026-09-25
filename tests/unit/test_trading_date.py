"""Phase 11 -- New York trading-date helpers (11-SPEC: 'trading day' = America/New_York date)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from ai_hedge_fund.db.dates import market_midnight_utc, trading_date


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        (datetime(2026, 9, 2, 23, 30, tzinfo=UTC), date(2026, 9, 2)),  # 19:30 EDT
        (datetime(2026, 9, 3, 3, 59, tzinfo=UTC), date(2026, 9, 2)),  # 23:59 EDT
        (datetime(2026, 9, 3, 4, 30, tzinfo=UTC), date(2026, 9, 3)),  # 00:30 EDT
        (datetime(2026, 12, 2, 4, 30, tzinfo=UTC), date(2026, 12, 1)),  # 23:30 EST
    ],
)
def test_trading_date_is_new_york_date(utc: datetime, expected: date) -> None:
    """11-PREMORTEM #11."""
    assert trading_date(utc) == expected


def test_trading_date_accepts_other_offsets() -> None:
    tokyo = datetime(2026, 9, 3, 8, 0, tzinfo=timezone(timedelta(hours=9)))  # 23:00Z Sep 2
    assert trading_date(tokyo) == date(2026, 9, 2)


def test_trading_date_rejects_naive() -> None:
    with pytest.raises(ValueError, match="aware"):
        trading_date(datetime(2026, 9, 2, 12, 0))


def test_market_midnight_utc_tracks_dst() -> None:
    assert market_midnight_utc(date(2026, 9, 15)) == datetime(2026, 9, 15, 4, 0, tzinfo=UTC)
    assert market_midnight_utc(date(2026, 12, 15)) == datetime(2026, 12, 15, 5, 0, tzinfo=UTC)
