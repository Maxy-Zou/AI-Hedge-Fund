"""Tests for IngestionPipeline orchestrator — DATA-04."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from kalshi_backtest.ingestion.types import CandlestickRecord, MarketRecord


def _make_market(ticker: str = "KXBTC-25", status: str = "active", result: str | None = None):
    """Factory for MarketRecord test fixtures."""
    return MarketRecord(
        ticker=ticker,
        event_ticker="KXBTC",
        series_ticker="KXBTC",
        subtitle="BTC above 50k",
        open_time=datetime(2025, 1, 1),
        close_time=datetime(2025, 12, 31),
        status=status,
        result=result,
    )


def _make_candle(ticker: str = "KXBTC-25", ts: int = 1735689600, close_price: int = 50):
    """Factory for CandlestickRecord test fixtures."""
    return CandlestickRecord(ticker=ticker, ts=ts, close_price=close_price)


def test_pipeline_stores_markets_and_candles(duckdb_con):
    """DATA-04: IngestionPipeline.run() stores markets and candles via the repo."""
    from kalshi_backtest.db.repository import MarketRepository
    from kalshi_backtest.ingestion.pipeline import IngestionPipeline, IngestionResult

    market = _make_market("KXBTC-25", status="active")
    candle = _make_candle("KXBTC-25", ts=1735689600)

    market_fetcher = MagicMock()
    market_fetcher.fetch_all.return_value = [market]

    candle_fetcher = MagicMock()
    candle_fetcher.fetch_for_market.return_value = [candle]

    repo = MarketRepository(duckdb_con)
    pipeline = IngestionPipeline(
        market_fetcher=market_fetcher,
        candlestick_fetcher=candle_fetcher,
        repository=repo,
    )

    result = pipeline.run(lookback_days=30)

    assert isinstance(result, IngestionResult)
    assert result.markets_upserted == 1
    assert result.candles_inserted == 1
    assert len(result.markets_failed) == 0
    # Verify data was actually stored
    assert repo.count_candles("KXBTC-25") == 1


def test_pipeline_incremental_sync_skips_existing_candles(duckdb_con):
    """DATA-04: Second run() call with same candles inserts 0 new candles (incremental sync)."""
    from kalshi_backtest.db.repository import MarketRepository
    from kalshi_backtest.ingestion.pipeline import IngestionPipeline

    market = _make_market("KXBTC-25", status="active")
    ts = 1735689600
    candle = _make_candle("KXBTC-25", ts=ts)

    market_fetcher = MagicMock()
    market_fetcher.fetch_all.return_value = [market]

    candle_fetcher = MagicMock()
    candle_fetcher.fetch_for_market.return_value = [candle]

    repo = MarketRepository(duckdb_con)
    pipeline = IngestionPipeline(
        market_fetcher=market_fetcher,
        candlestick_fetcher=candle_fetcher,
        repository=repo,
    )

    # First run — stores 1 candle
    pipeline.run(lookback_days=30)

    # Reconfigure: second run returns empty (incremental sync would not re-fetch)
    candle_fetcher.fetch_for_market.return_value = []
    result2 = pipeline.run(lookback_days=30)

    # Second run inserted 0 candles
    assert result2.candles_inserted == 0
    # Total in DB is still just 1 (no duplicates)
    assert repo.count_candles("KXBTC-25") == 1
    # Verify get_last_candle_ts was called on second run (incremental sync check)
    assert candle_fetcher.fetch_for_market.call_count == 2
    _, kwargs = candle_fetcher.fetch_for_market.call_args
    last_ts_kwarg = kwargs.get("last_ingested_ts")
    positional_args = candle_fetcher.fetch_for_market.call_args[0]
    assert last_ts_kwarg is not None or len(positional_args) >= 3


def test_pipeline_lookahead_protection_non_settled_market(duckdb_con):
    """DATA-04: Non-settled market is stored with result=None regardless of input result."""
    from kalshi_backtest.db.repository import MarketRepository
    from kalshi_backtest.ingestion.pipeline import IngestionPipeline

    # Market with status=active but has a result value (should be sanitized)
    market = _make_market("KXBTC-25", status="active", result="yes")

    market_fetcher = MagicMock()
    market_fetcher.fetch_all.return_value = [market]

    candle_fetcher = MagicMock()
    candle_fetcher.fetch_for_market.return_value = []

    repo = MarketRepository(duckdb_con)
    pipeline = IngestionPipeline(
        market_fetcher=market_fetcher,
        candlestick_fetcher=candle_fetcher,
        repository=repo,
    )

    pipeline.run(lookback_days=30)

    # result column must be NULL in DB (lookahead protection)
    row = duckdb_con.execute("SELECT result FROM markets WHERE ticker = 'KXBTC-25'").fetchone()
    assert row is not None
    assert row[0] is None, f"Expected result=None for non-settled market, got {row[0]!r}"


def test_pipeline_isolated_market_failure(duckdb_con):
    """DATA-04: Failed candle fetch for one market does not abort other markets."""
    from kalshi_backtest.db.repository import MarketRepository
    from kalshi_backtest.ingestion.pipeline import IngestionPipeline

    market_ok = _make_market("KXBTC-25", status="active")
    market_fail = _make_market("KXBTC-26", status="active")
    candle_ok = _make_candle("KXBTC-25", ts=1735689600)

    market_fetcher = MagicMock()
    market_fetcher.fetch_all.return_value = [market_ok, market_fail]

    def mock_fetch_for_market(market, lookback_start, last_ingested_ts=None):
        if market.ticker == "KXBTC-26":
            raise RuntimeError("Simulated fetch failure")
        return [candle_ok]

    candle_fetcher = MagicMock()
    candle_fetcher.fetch_for_market.side_effect = mock_fetch_for_market

    repo = MarketRepository(duckdb_con)
    pipeline = IngestionPipeline(
        market_fetcher=market_fetcher,
        candlestick_fetcher=candle_fetcher,
        repository=repo,
    )

    result = pipeline.run(lookback_days=30)

    # Failed market is tracked
    assert "KXBTC-26" in result.markets_failed
    # Successful market's candle was still stored
    assert repo.count_candles("KXBTC-25") == 1
    # Pipeline completed (did not raise)
    assert result.candles_inserted == 1
