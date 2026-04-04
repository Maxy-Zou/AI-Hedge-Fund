"""DuckDB schema DDL and connection factory for the Kalshi backtesting store.

Schema design decisions:
- TIMESTAMP (naive UTC) not TIMESTAMPTZ — DuckDB 1.5.1 requires pytz for TIMESTAMPTZ;
  all datetimes are stored as naive UTC and documented as such.
- candles PRIMARY KEY (ticker, ts) enables ON CONFLICT DO NOTHING for idempotent inserts.
- markets uses ON CONFLICT DO UPDATE for status/result — these fields change on settlement.
- result column is NULL for unsettled markets — lookahead protection enforced at
  application layer (ingestion only writes result when status='settled').
"""
from __future__ import annotations

from pathlib import Path

import duckdb


SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS markets (
    ticker          VARCHAR NOT NULL PRIMARY KEY,
    event_ticker    VARCHAR NOT NULL,
    series_ticker   VARCHAR NOT NULL,
    subtitle        TEXT,
    open_time       TIMESTAMP NOT NULL,
    close_time      TIMESTAMP NOT NULL,
    expiration_time TIMESTAMP,
    status          VARCHAR NOT NULL,
    result          VARCHAR,
    ingested_at     TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS candles (
    ticker          VARCHAR NOT NULL,
    ts              TIMESTAMP NOT NULL,
    open_price      INTEGER,
    high_price      INTEGER,
    low_price       INTEGER,
    close_price     INTEGER NOT NULL,
    volume          INTEGER,
    ingested_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, ts)
);

CREATE INDEX IF NOT EXISTS idx_candles_ticker ON candles(ticker);
CREATE INDEX IF NOT EXISTS idx_candles_ts ON candles(ts);
CREATE INDEX IF NOT EXISTS idx_markets_event ON markets(event_ticker);
CREATE INDEX IF NOT EXISTS idx_markets_series ON markets(series_ticker);
CREATE INDEX IF NOT EXISTS idx_markets_close_time ON markets(close_time);
"""


def get_connection(db_path: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection. Default is in-memory (for tests).

    Args:
        db_path: Path to .duckdb file, or ':memory:' for in-memory.

    Returns:
        Open DuckDB connection. Caller is responsible for closing.
    """
    return duckdb.connect(str(db_path))


def apply_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Apply the Phase 1 schema DDL to an existing connection.

    Idempotent — uses CREATE TABLE IF NOT EXISTS throughout.

    Args:
        con: Open DuckDB connection to apply schema to.
    """
    con.execute(SCHEMA_DDL)


def get_or_create_db(db_path: str | Path) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection and apply schema (creates DB if not exists).

    Args:
        db_path: Path to .duckdb file.

    Returns:
        Open DuckDB connection with schema applied.
    """
    con = get_connection(db_path)
    apply_schema(con)
    return con
