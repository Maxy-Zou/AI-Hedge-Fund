"""Shared pytest fixtures for kalshi-backtest tests.

Provides:
    duckdb_con: In-memory DuckDB connection with schema applied (reusable fixture).
    load_fixture: Fixture factory returning a callable that loads JSON fixture files.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from kalshi_backtest.db.schema import SCHEMA_DDL, apply_schema

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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


__all__ = ["SCHEMA_DDL", "duckdb_con", "load_fixture"]
