"""MarketRepository — typed interface for all DuckDB reads and writes.

The simulation engine and ingestion pipeline access the database
exclusively through this class. Raw SQL stays here — no SQL in
business logic layers.

Security: All variable data uses parameterized queries (? placeholders).
          No f-string SQL construction anywhere in this file except for
          dynamically-built WHERE clauses where column names (not values)
          are concatenated — these carry # noqa: S608 annotations.
"""
from __future__ import annotations

from datetime import datetime

import duckdb
import structlog

from kalshi_backtest.ingestion.types import CandlestickRecord, MarketRecord

logger = structlog.get_logger(__name__)

_INSERT_MARKET = """
    INSERT INTO markets
        (ticker, event_ticker, series_ticker, subtitle, open_time, close_time,
         expiration_time, status, result, ingested_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (ticker) DO UPDATE SET
        status      = excluded.status,
        result      = excluded.result,
        ingested_at = excluded.ingested_at
"""

_INSERT_CANDLE = """
    INSERT INTO candles
        (ticker, ts, open_price, high_price, low_price, close_price, volume, ingested_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT DO NOTHING
"""

_GET_LAST_CANDLE_TS = """
    SELECT MAX(EPOCH(ts))::BIGINT FROM candles WHERE ticker = ?
"""

_COUNT_CANDLES = """
    SELECT COUNT(*) FROM candles WHERE ticker = ?
"""


class MarketRepository:
    """Typed data access layer for the DuckDB backtesting store.

    Args:
        con: Open DuckDB connection with schema applied.
    """

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def upsert_market(self, market: MarketRecord) -> None:
        """Insert or update a market record.

        Markets are upserted because status and result change on settlement.
        Uses ON CONFLICT DO UPDATE on ticker (primary key).

        Args:
            market: Validated MarketRecord to store.
        """
        now = datetime.now().replace(tzinfo=None)
        self._con.execute(_INSERT_MARKET, [
            market.ticker,
            market.event_ticker,
            market.series_ticker,
            market.subtitle,
            market.open_time,
            market.close_time,
            market.expiration_time,
            market.status,
            market.result,
            now,
        ])

    def insert_candles(self, candles: list[CandlestickRecord]) -> int:
        """Insert candlestick rows, skipping duplicates.

        Uses ON CONFLICT DO NOTHING on PRIMARY KEY (ticker, ts).
        Append-only — never overwrites existing candle data.

        Args:
            candles: List of CandlestickRecord to insert.

        Returns:
            Number of rows passed for insertion (not actual inserts — DuckDB
            executemany doesn't expose rows-affected count reliably).
        """
        if not candles:
            return 0

        now = datetime.now().replace(tzinfo=None)
        rows = [
            (c.ticker, c.ts, c.open_price, c.high_price, c.low_price, c.close_price, c.volume, now)
            for c in candles
        ]
        self._con.executemany(_INSERT_CANDLE, rows)
        logger.debug("candles_insert_attempted", count=len(candles), ticker=candles[0].ticker)
        return len(candles)

    def get_last_candle_ts(self, ticker: str) -> int | None:
        """Return Unix epoch of the most recent candle for a ticker.

        Used for incremental sync — the next fetch starts from this ts + 1 day.

        Args:
            ticker: Market ticker to query.

        Returns:
            Unix epoch integer of MAX(ts), or None if no candles exist.
        """
        row = self._con.execute(_GET_LAST_CANDLE_TS, [ticker]).fetchone()
        return row[0] if row and row[0] is not None else None

    def count_candles(self, ticker: str) -> int:
        """Count total candle rows stored for a ticker.

        Args:
            ticker: Market ticker to count.

        Returns:
            Number of candle rows in the database for this ticker.
        """
        row = self._con.execute(_COUNT_CANDLES, [ticker]).fetchone()
        return row[0] if row else 0

    def get_markets(
        self,
        series_ticker: str | None = None,
        min_close_time: datetime | None = None,
        max_close_time: datetime | None = None,
    ) -> list[dict]:
        """Query markets with optional filters.

        Args:
            series_ticker: Filter by series (e.g. 'KXBTC'). None = all.
            min_close_time: Exclude markets closing before this time (naive UTC).
            max_close_time: Exclude markets closing after this time (naive UTC).

        Returns:
            List of dicts with all markets columns.
        """
        conditions = []
        params: list = []

        if series_ticker is not None:
            conditions.append("series_ticker = ?")
            params.append(series_ticker)
        if min_close_time is not None:
            conditions.append("close_time >= ?")
            params.append(min_close_time)
        if max_close_time is not None:
            conditions.append("close_time <= ?")
            params.append(max_close_time)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM markets {where} ORDER BY close_time"  # noqa: S608
        return self._con.execute(sql, params).fetchdf().to_dict("records")

    def get_candles(
        self,
        ticker: str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> list[dict]:
        """Fetch candle rows for a ticker within an optional date range.

        Args:
            ticker: Market ticker.
            start_ts: Include candles at or after this timestamp (naive UTC).
            end_ts: Include candles at or before this timestamp (naive UTC).

        Returns:
            List of dicts with all candles columns, ordered by ts ascending.
        """
        conditions = ["ticker = ?"]
        params: list = [ticker]

        if start_ts is not None:
            conditions.append("ts >= ?")
            params.append(start_ts)
        if end_ts is not None:
            conditions.append("ts <= ?")
            params.append(end_ts)

        where = f"WHERE {' AND '.join(conditions)}"
        sql = f"SELECT * FROM candles {where} ORDER BY ts"  # noqa: S608
        return self._con.execute(sql, params).fetchdf().to_dict("records")
