"""Shared pytest fixtures for kalshi-backtest tests.

Provides:
    duckdb_con: In-memory DuckDB connection with schema applied (reusable fixture).
    load_fixture: Fixture factory returning a callable that loads JSON fixture files.
    sqlite_signals_db: Tuple of (db_url, connection) for InsiderTrackerAdapter unit tests.
    insert_signal_row: Helper to insert rows into the in-memory signals table.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Generator

import duckdb
import pytest

from kalshi_backtest.db.schema import SCHEMA_DDL, apply_schema

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_SIGNALS_DDL = """
CREATE TABLE IF NOT EXISTS signals (
    ticker      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    confidence  REAL NOT NULL,
    details     TEXT,
    detected_at TEXT NOT NULL
)
"""


@pytest.fixture()
def duckdb_con() -> duckdb.DuckDBPyConnection:
    """Fresh in-memory DuckDB connection with schema applied.

    Each test gets an isolated database — no state leaks between tests.
    """
    con = duckdb.connect(":memory:")
    apply_schema(con)
    return con


@pytest.fixture()
def load_fixture():
    """Fixture factory: returns a callable that loads JSON fixtures from tests/fixtures/.

    Usage in tests:
        def test_something(load_fixture):
            data = load_fixture("markets.json")

    Returns:
        Callable[[str], dict | list]: loads and parses the named JSON file.
    """

    def _load(name: str) -> dict | list:
        """Load a JSON fixture file from tests/fixtures/.

        Args:
            name: Filename without path (e.g. 'markets.json').

        Returns:
            Parsed JSON content as dict or list.

        Raises:
            FileNotFoundError: If the fixture file does not exist.
        """
        path = FIXTURES_DIR / name
        with path.open() as f:
            return json.load(f)

    return _load


@pytest.fixture()
def sqlite_signals_db() -> Generator[tuple[str, sqlite3.Connection], None, None]:
    """SQLite on-disk temp database with a signals table for InsiderTrackerAdapter tests.

    Uses a temporary file so the adapter can open it by URL. Yields a tuple of:
        - db_url: SQLite URL string in the form 'sqlite:///path/to/file.db'
        - conn: Open sqlite3.Connection for inserting test rows via insert_signal_row()

    The temp file is cleaned up after the test completes.

    Yields:
        tuple[str, sqlite3.Connection]: (db_url, connection)
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.execute(_SIGNALS_DDL)
    conn.commit()

    db_url = f"sqlite:///{db_path}"
    try:
        yield db_url, conn
    finally:
        conn.close()
        Path(db_path).unlink(missing_ok=True)


def insert_signal_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    signal_type: str = "volume_spike",
    confidence: float = 0.9,
    details: str = "{}",
    detected_at: str = "2024-01-10T12:00:00",
) -> None:
    """Helper: insert a single row into the in-memory signals table.

    Args:
        conn: sqlite3.Connection from the sqlite_signals_db fixture.
        ticker: Market ticker for the signal.
        signal_type: One of 'volume_spike', 'price_move', 'timing_cluster'.
        confidence: Signal confidence in [0.0, 1.0].
        details: JSON string with signal metadata.
        detected_at: ISO-8601 UTC datetime string.
    """
    conn.execute(
        "INSERT INTO signals (ticker, signal_type, confidence, details, detected_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ticker, signal_type, confidence, details, detected_at),
    )
    conn.commit()


__all__ = ["SCHEMA_DDL", "duckdb_con", "insert_signal_row", "load_fixture", "sqlite_signals_db"]
