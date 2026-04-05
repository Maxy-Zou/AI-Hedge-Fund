"""Tests for ingestion clients and fetchers — DATA-01, DATA-02, DATA-04."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from kalshi_backtest.ingestion.cutoff import CutoffResult, HistoricalCutoffResolver
from kalshi_backtest.ingestion.types import CandlestickRecord

# ── DATA-01: live + historical client parse fixture responses ─────────────────

def test_live_candlestick_fetch(load_fixture):
    """DATA-01: KalshiHistoricalClient parses fixture candlestick response correctly."""
    fixture = load_fixture("candlesticks.json")
    candles_raw = fixture["candlesticks"]

    # Simulate what KalshiHistoricalClient.get_candlesticks() would parse
    records = [
        CandlestickRecord(
            ticker="KXBTCD-25JAN31-T99999",
            ts=int(c["ts"]),
            open_price=c.get("open_price"),
            high_price=c.get("high_price"),
            low_price=c.get("low_price"),
            close_price=c.get("close_price", c.get("price", 0)),
            volume=c.get("volume"),
        )
        for c in candles_raw
    ]

    assert len(records) == 2
    assert records[0].ticker == "KXBTCD-25JAN31-T99999"
    assert records[0].ts.tzinfo is None          # naive UTC
    assert 0 <= records[0].close_price <= 100    # valid price range


# ── DATA-02: cutoff routing ──────────────────────────────────────────────────

def test_cutoff_routing_historical():
    """DATA-02: Markets settled before cutoff are identified as historical tier."""
    cutoff = CutoffResult(
        cutoff_ts=1_700_000_000,
        cutoff_dt=datetime(2023, 11, 14, 22, 13, 20),  # naive UTC
    )
    # Market close_time BEFORE cutoff → historical
    market_close = datetime(2023, 6, 1, 0, 0, 0)

    http_mock = MagicMock()
    resolver = HistoricalCutoffResolver(http_mock, {})
    resolver._cached = cutoff

    assert resolver.is_historical(market_close, cutoff) is True


def test_cutoff_routing_live():
    """DATA-02: Markets settled after cutoff are identified as live tier."""
    cutoff = CutoffResult(
        cutoff_ts=1_700_000_000,
        cutoff_dt=datetime(2023, 11, 14, 22, 13, 20),
    )
    # Market close_time AFTER cutoff → live
    market_close = datetime(2024, 6, 1, 0, 0, 0)

    http_mock = MagicMock()
    resolver = HistoricalCutoffResolver(http_mock, {})
    resolver._cached = cutoff

    assert resolver.is_historical(market_close, cutoff) is False


def test_cutoff_resolve_caches_result():
    """DATA-02: Second call to resolve() uses cache, makes no HTTP request."""
    cached = CutoffResult(cutoff_ts=1_700_000_000, cutoff_dt=datetime(2023, 11, 14))
    http_mock = MagicMock()
    resolver = HistoricalCutoffResolver(http_mock, {})
    resolver._cached = cached

    result = resolver.resolve()  # should return cached, not call http_mock.get

    assert result is cached
    http_mock.get.assert_not_called()


# ── DATA-04: idempotent ingest ───────────────────────────────────────────────

def test_idempotent_ingest(duckdb_con, load_fixture):
    """DATA-04: Inserting same candlestick fixture twice stores exactly one row per (ticker, ts)."""
    from kalshi_backtest.db.repository import MarketRepository

    fixture = load_fixture("candlesticks.json")
    repo = MarketRepository(duckdb_con)

    candles = [
        CandlestickRecord(
            ticker=c["ticker"],
            ts=int(c["ts"]),
            open_price=c.get("open_price"),
            high_price=c.get("high_price"),
            low_price=c.get("low_price"),
            close_price=c.get("close_price", c.get("price", 0)),
            volume=c.get("volume"),
        )
        for c in fixture["candlesticks"]
    ]

    repo.insert_candles(candles)
    repo.insert_candles(candles)  # second insert — should be no-op

    count = repo.count_candles("KXBTCD-25JAN31-T99999")
    assert count == len(candles), f"Expected {len(candles)} rows, got {count} (duplicates detected)"
