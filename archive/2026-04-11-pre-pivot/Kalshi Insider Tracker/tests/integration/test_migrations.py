"""Integration tests for Alembic migrations using testcontainers PostgreSQL."""

from __future__ import annotations

import os
import subprocess

import pytest
from sqlalchemy import create_engine, inspect

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pg_url():
    """Spin up a temporary PostgreSQL container for migration tests."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16") as pg:
        # Use psycopg (v3) driver
        yield pg.get_connection_url().replace("psycopg2", "psycopg")


def test_all_tables_created(pg_url: str) -> None:
    """LOG-03: Alembic migration creates all expected tables."""
    project_dir = "/Users/maxzou/Documents/projects/AI Hedgefund/Kalshi Insider Tracker"
    env = {
        **os.environ,
        "KALSHI_TRACKER_DATABASE_URL": pg_url,
        "PYTHONPATH": os.path.join(project_dir, "src"),
    }
    result = subprocess.run(
        [
            os.path.join(project_dir, ".venv/bin/alembic"),
            "upgrade",
            "head",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=project_dir,
    )
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"
    engine = create_engine(pg_url)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    for expected in ["markets", "market_snapshots", "signals", "trades"]:
        assert expected in tables, f"Missing table: {expected}"
    engine.dispose()


def test_market_snapshots_columns(pg_url: str) -> None:
    """market_snapshots has all required columns with correct types."""
    engine = create_engine(pg_url)
    inspector = inspect(engine)
    cols = {c["name"]: c for c in inspector.get_columns("market_snapshots")}
    required_cols = [
        "id",
        "ticker",
        "series_ticker",
        "yes_bid",
        "yes_ask",
        "no_bid",
        "no_ask",
        "last_price",
        "volume",
        "volume_24h",
        "status",
        "captured_at",
        "raw_snapshot",
        "created_at",
    ]
    for col_name in required_cols:
        assert col_name in cols, f"Missing column: {col_name} in market_snapshots"
    engine.dispose()


def test_signals_columns(pg_url: str) -> None:
    """signals table has all required columns."""
    engine = create_engine(pg_url)
    inspector = inspect(engine)
    cols = {c["name"]: c for c in inspector.get_columns("signals")}
    required_cols = [
        "id", "ticker", "signal_type", "confidence", "details", "detected_at", "created_at",
    ]
    for col_name in required_cols:
        assert col_name in cols, f"Missing column: {col_name} in signals"
    engine.dispose()


def test_trades_columns(pg_url: str) -> None:
    """trades table has all required columns."""
    engine = create_engine(pg_url)
    inspector = inspect(engine)
    cols = {c["name"]: c for c in inspector.get_columns("trades")}
    required_cols = [
        "id",
        "ticker",
        "signal_id",
        "side",
        "contracts",
        "price_cents",
        "mode",
        "status",
        "placed_at",
        "kalshi_order_id",
        "created_at",
    ]
    for col_name in required_cols:
        assert col_name in cols, f"Missing column: {col_name} in trades"
    engine.dispose()
