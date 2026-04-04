"""Shared pytest fixtures for kalshi-backtest tests."""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"

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
CREATE INDEX IF NOT EXISTS idx_markets_close_time ON markets(close_time);
"""


@pytest.fixture()
def duckdb_con() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with Phase 1 schema applied. Isolated per test."""
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA_DDL)
    yield con
    con.close()


@pytest.fixture()
def load_fixture():
    """Returns a function that loads a JSON fixture file by name."""
    def _load(name: str) -> dict:
        path = FIXTURES_DIR / name
        with path.open() as f:
            return json.load(f)
    return _load
