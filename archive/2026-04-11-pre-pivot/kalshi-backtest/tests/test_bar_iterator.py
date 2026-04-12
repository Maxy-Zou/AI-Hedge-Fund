"""TDD tests for BarIterator — look-ahead prevention and chronological ordering.

These tests verify the core invariants of the replay engine:
- All bars yielded in non-decreasing ts order across multiple tickers
- result=None enforced for every bar where ts < market.close_time (look-ahead firewall)
- result exposed when ts >= close_time AND market.result is not None
- All tickers appear in output
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from kalshi_backtest.simulation.bar_iterator import BarIterator
from kalshi_backtest.simulation.snapshot import MarketSnapshot

# ---------------------------------------------------------------------------
# Helpers: build minimal market and candle dicts for testing
# ---------------------------------------------------------------------------

T0 = datetime(2024, 1, 1, 12, 0, 0)  # naive UTC baseline


def _market(
    ticker: str,
    close_time: datetime,
    result: str | None = "yes",
    event_ticker: str = "EV-TEST",
    series_ticker: str = "SR-TEST",
) -> dict:
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "series_ticker": series_ticker,
        "close_time": close_time,
        "result": result,
        "subtitle": None,
    }


def _candle(ticker: str, ts: datetime, close_price: int = 50) -> dict:
    return {
        "ticker": ticker,
        "ts": ts,
        "close_price": close_price,
    }


# ---------------------------------------------------------------------------
# Chronological ordering
# ---------------------------------------------------------------------------


def test_bars_are_chronological() -> None:
    """Bars from multiple tickers must come out in non-decreasing ts order."""
    # Market A closes in 3 days, Market B in 2 days
    close_a = T0 + timedelta(days=3)
    close_b = T0 + timedelta(days=2)

    market_a = _market("TICKER-A", close_time=close_a)
    market_b = _market("TICKER-B", close_time=close_b)

    # Interleave candles: A at T+0, B at T+1h, A at T+2h, B at T+3h
    candles_by_ticker = {
        "TICKER-A": [
            _candle("TICKER-A", T0),
            _candle("TICKER-A", T0 + timedelta(hours=2)),
        ],
        "TICKER-B": [
            _candle("TICKER-B", T0 + timedelta(hours=1)),
            _candle("TICKER-B", T0 + timedelta(hours=3)),
        ],
    }

    iterator = BarIterator(markets=[market_a, market_b], candles_by_ticker=candles_by_ticker)
    snapshots = list(iterator)

    timestamps = [s.ts for s in snapshots]
    assert timestamps == sorted(timestamps), "Snapshots must be in non-decreasing ts order"


def test_all_tickers_in_output() -> None:
    """Both tickers must appear in the iteration output."""
    close = T0 + timedelta(days=3)
    market_a = _market("TICKER-A", close_time=close)
    market_b = _market("TICKER-B", close_time=close)

    candles_by_ticker = {
        "TICKER-A": [_candle("TICKER-A", T0)],
        "TICKER-B": [_candle("TICKER-B", T0 + timedelta(hours=1))],
    }

    iterator = BarIterator(markets=[market_a, market_b], candles_by_ticker=candles_by_ticker)
    snapshots = list(iterator)

    tickers = {s.ticker for s in snapshots}
    assert "TICKER-A" in tickers
    assert "TICKER-B" in tickers


# ---------------------------------------------------------------------------
# Look-ahead firewall: result suppressed before close_time
# ---------------------------------------------------------------------------


def test_result_suppressed_before_close_time() -> None:
    """Bar at T0 with close_time=T0+1d must have result=None."""
    close = T0 + timedelta(days=1)
    market = _market("TICKER-A", close_time=close, result="yes")
    candles_by_ticker = {"TICKER-A": [_candle("TICKER-A", T0)]}

    iterator = BarIterator(markets=[market], candles_by_ticker=candles_by_ticker)
    snapshots = list(iterator)

    assert len(snapshots) == 1
    assert snapshots[0].result is None, "result must be None before close_time"


def test_result_suppressed_at_bar_before_close() -> None:
    """Bar at exactly close_time - 1 second must have result=None."""
    close = T0 + timedelta(days=1)
    bar_ts = close - timedelta(seconds=1)

    market = _market("TICKER-A", close_time=close, result="yes")
    candles_by_ticker = {"TICKER-A": [_candle("TICKER-A", bar_ts)]}

    iterator = BarIterator(markets=[market], candles_by_ticker=candles_by_ticker)
    snapshots = list(iterator)

    assert snapshots[0].result is None, "result must be None when ts < close_time (by 1 second)"


# ---------------------------------------------------------------------------
# Look-ahead firewall: result exposed at and after close_time
# ---------------------------------------------------------------------------


def test_result_exposed_at_close_time() -> None:
    """Bar at exactly close_time must expose result when market.result is not None."""
    close = T0 + timedelta(days=1)

    market = _market("TICKER-A", close_time=close, result="yes")
    candles_by_ticker = {"TICKER-A": [_candle("TICKER-A", close)]}  # ts == close_time

    iterator = BarIterator(markets=[market], candles_by_ticker=candles_by_ticker)
    snapshots = list(iterator)

    assert snapshots[0].result == "yes", "result must be exposed when ts == close_time"


def test_result_exposed_after_close_time() -> None:
    """Bar after close_time must expose result when market.result is not None."""
    close = T0 + timedelta(days=1)
    bar_ts = close + timedelta(days=1)  # one day after close

    market = _market("TICKER-A", close_time=close, result="yes")
    candles_by_ticker = {"TICKER-A": [_candle("TICKER-A", bar_ts)]}

    iterator = BarIterator(markets=[market], candles_by_ticker=candles_by_ticker)
    snapshots = list(iterator)

    assert snapshots[0].result == "yes", "result must be exposed when ts > close_time"


def test_result_none_when_db_result_is_none() -> None:
    """Even when ts >= close_time, if market.result is None in DB, snapshot.result is None."""
    close = T0 + timedelta(days=1)
    bar_ts = close  # at close_time

    market = _market("TICKER-A", close_time=close, result=None)  # DB has no result yet
    candles_by_ticker = {"TICKER-A": [_candle("TICKER-A", bar_ts)]}

    iterator = BarIterator(markets=[market], candles_by_ticker=candles_by_ticker)
    snapshots = list(iterator)

    assert snapshots[0].result is None, "result must stay None when DB has no result"


# ---------------------------------------------------------------------------
# bar_count helper
# ---------------------------------------------------------------------------


def test_bar_count() -> None:
    """bar_count returns total number of candles across all tickers."""
    close = T0 + timedelta(days=5)
    market_a = _market("TICKER-A", close_time=close)
    market_b = _market("TICKER-B", close_time=close)

    candles_by_ticker = {
        "TICKER-A": [_candle("TICKER-A", T0), _candle("TICKER-A", T0 + timedelta(hours=1))],
        "TICKER-B": [_candle("TICKER-B", T0 + timedelta(hours=2))],
    }

    iterator = BarIterator(markets=[market_a, market_b], candles_by_ticker=candles_by_ticker)
    assert iterator.bar_count() == 3


# ---------------------------------------------------------------------------
# Edge case: empty candles
# ---------------------------------------------------------------------------


def test_empty_candles_yields_nothing() -> None:
    """BarIterator with no candles yields no snapshots without error."""
    close = T0 + timedelta(days=1)
    market = _market("TICKER-A", close_time=close)

    iterator = BarIterator(markets=[market], candles_by_ticker={})
    snapshots = list(iterator)

    assert snapshots == []
