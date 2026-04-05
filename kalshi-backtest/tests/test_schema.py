"""Tests for DuckDB schema DDL and MarketRepository data access layer.

Covers:
- Schema creation (both tables + all indexes)
- Idempotent candle inserts (ON CONFLICT DO NOTHING)
- Market upsert behavior (status/result update on conflict)
- NULL result for unsettled markets (lookahead safety)
- get_last_candle_ts() returns None when no candles exist
- UTC timestamp roundtrip through DuckDB
"""
from __future__ import annotations

from datetime import UTC, datetime

import duckdb
import pytest


@pytest.fixture()
def mem_db() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with schema applied."""
    from kalshi_backtest.db.schema import apply_schema, get_connection

    con = get_connection(":memory:")
    apply_schema(con)
    return con


@pytest.fixture()
def repo(mem_db: duckdb.DuckDBPyConnection):
    """MarketRepository bound to in-memory DB."""
    from kalshi_backtest.db.repository import MarketRepository

    return MarketRepository(mem_db)


def _make_market(ticker: str = "KXBTC-25", status: str = "active", result: str | None = None):
    """Factory for MarketRecord test fixtures."""
    from kalshi_backtest.ingestion.types import MarketRecord

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
    from kalshi_backtest.ingestion.types import CandlestickRecord

    return CandlestickRecord(ticker=ticker, ts=ts, close_price=close_price)


class TestSchemaCreation:
    """Schema DDL creates correct tables and indexes."""

    def test_apply_schema_creates_markets_table(self, mem_db: duckdb.DuckDBPyConnection) -> None:
        """apply_schema creates the markets table without error."""
        tables = mem_db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'markets'"
        ).fetchall()
        assert len(tables) == 1

    def test_apply_schema_creates_candles_table(self, mem_db: duckdb.DuckDBPyConnection) -> None:
        """apply_schema creates the candles table without error."""
        tables = mem_db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'candles'"
        ).fetchall()
        assert len(tables) == 1

    def test_apply_schema_idempotent(self, mem_db: duckdb.DuckDBPyConnection) -> None:
        """Calling apply_schema twice does not raise (CREATE TABLE IF NOT EXISTS)."""
        from kalshi_backtest.db.schema import apply_schema

        apply_schema(mem_db)  # second call should be a no-op

    def test_schema_ddl_constant_is_string(self) -> None:
        """SCHEMA_DDL is a non-empty string."""
        from kalshi_backtest.db.schema import SCHEMA_DDL

        assert isinstance(SCHEMA_DDL, str)
        assert len(SCHEMA_DDL) > 100


class TestMarketUpsert:
    """MarketRepository.upsert_market() insert and update behavior."""

    def test_insert_new_market(self, repo, mem_db: duckdb.DuckDBPyConnection) -> None:
        """upsert_market inserts a new market row."""
        repo.upsert_market(_make_market("KXBTC-25"))
        count = mem_db.execute("SELECT COUNT(*) FROM markets WHERE ticker = 'KXBTC-25'").fetchone()
        assert count[0] == 1

    def test_null_result_for_unsettled_market(  # noqa: E501
        self, repo, mem_db: duckdb.DuckDBPyConnection
    ) -> None:
        """Unsettled market stores NULL in result column (lookahead_safe_schema)."""
        repo.upsert_market(_make_market("KXBTC-25", status="active", result=None))
        row = mem_db.execute("SELECT result FROM markets WHERE ticker = 'KXBTC-25'").fetchone()
        assert row[0] is None

    def test_upsert_updates_status_and_result(  # noqa: E501
        self, repo, mem_db: duckdb.DuckDBPyConnection
    ) -> None:
        """upsert_market overwrites status and result on conflict (settled market)."""
        repo.upsert_market(_make_market("KXBTC-25", status="active", result=None))
        repo.upsert_market(_make_market("KXBTC-25", status="settled", result="yes"))
        query = "SELECT status, result FROM markets WHERE ticker = 'KXBTC-25'"
        row = mem_db.execute(query).fetchone()
        assert row[0] == "settled"
        assert row[1] == "yes"

    def test_single_row_after_two_upserts(self, repo, mem_db: duckdb.DuckDBPyConnection) -> None:
        """Upserting same ticker twice results in exactly 1 row."""
        repo.upsert_market(_make_market("KXBTC-25"))
        repo.upsert_market(_make_market("KXBTC-25"))
        count = mem_db.execute("SELECT COUNT(*) FROM markets WHERE ticker = 'KXBTC-25'").fetchone()
        assert count[0] == 1


class TestCandleInsert:
    """MarketRepository.insert_candles() idempotency and counting."""

    def test_insert_candle_stores_row(self, repo, mem_db: duckdb.DuckDBPyConnection) -> None:
        """insert_candles stores a single candle row."""
        repo.insert_candles([_make_candle()])
        count = mem_db.execute("SELECT COUNT(*) FROM candles WHERE ticker = 'KXBTC-25'").fetchone()
        assert count[0] == 1

    def test_candle_insert_idempotent(self, repo, mem_db: duckdb.DuckDBPyConnection) -> None:
        """Inserting the same (ticker, ts) candle twice stores exactly 1 row."""
        candle = _make_candle()
        repo.insert_candles([candle])
        repo.insert_candles([candle])
        count = mem_db.execute("SELECT COUNT(*) FROM candles WHERE ticker = 'KXBTC-25'").fetchone()
        assert count[0] == 1

    def test_insert_empty_list_returns_zero(self, repo) -> None:
        """insert_candles with empty list returns 0 without error."""
        result = repo.insert_candles([])
        assert result == 0

    def test_count_candles(self, repo) -> None:
        """count_candles returns correct count after insertion."""
        candles = [_make_candle(ts=1735689600 + i * 86400) for i in range(5)]
        repo.insert_candles(candles)
        assert repo.count_candles("KXBTC-25") == 5

    def test_count_candles_empty(self, repo) -> None:
        """count_candles returns 0 when no candles exist for ticker."""
        assert repo.count_candles("NONEXISTENT") == 0


class TestGetLastCandleTs:
    """MarketRepository.get_last_candle_ts() behavior."""

    def test_returns_none_when_no_candles(self, repo) -> None:
        """get_last_candle_ts returns None when no candles exist for ticker."""
        result = repo.get_last_candle_ts("NONEXISTENT")
        assert result is None

    def test_returns_max_ts(self, repo) -> None:
        """get_last_candle_ts returns epoch of the most recent candle."""
        ts1 = 1735689600  # 2025-01-01 00:00:00 UTC
        ts2 = 1735689600 + 86400  # 2025-01-02 00:00:00 UTC
        repo.insert_candles([_make_candle(ts=ts1), _make_candle(ts=ts2)])
        result = repo.get_last_candle_ts("KXBTC-25")
        assert result == ts2


class TestDstTimestampRoundtrip:
    """Timestamp roundtrip through DuckDB preserves naive UTC values."""

    def test_dst_timestamp_roundtrip(self, repo, mem_db: duckdb.DuckDBPyConnection) -> None:
        """Naive UTC datetimes survive a DuckDB roundtrip unchanged (dst_timestamp_roundtrip)."""
        # Use a timestamp during DST transition (2025-03-09 02:00:00 US/Eastern = UTC 07:00:00)
        # Stored as naive UTC — no offset applied.
        ts_epoch = 1741500000  # 2025-03-09 07:00:00 UTC (DST transition day)
        from kalshi_backtest.ingestion.types import CandlestickRecord

        candle = CandlestickRecord(ticker="DST-TEST", ts=ts_epoch, close_price=50)
        repo.insert_candles([candle])

        rows = mem_db.execute("SELECT ts FROM candles WHERE ticker = 'DST-TEST'").fetchall()
        assert len(rows) == 1
        stored_ts = rows[0][0]
        # DuckDB returns naive datetime — verify it equals original naive UTC
        expected = datetime.fromtimestamp(ts_epoch, tz=UTC).replace(tzinfo=None)
        assert stored_ts == expected


class TestDbModuleExports:
    """kalshi_backtest.db module exports all expected symbols."""

    def test_db_module_exports(self) -> None:
        """All expected symbols are importable from kalshi_backtest.db."""
        from kalshi_backtest.db import (  # noqa: F401
            SCHEMA_DDL,
            MarketRepository,
            apply_schema,
            get_connection,
            get_or_create_db,
        )
