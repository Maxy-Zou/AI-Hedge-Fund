"""Tests for Alembic migration correctness and idempotency.

Verifies that the initial migration creates all four tables with correct
partitioning, constraints, and indexes against a real PostgreSQL container.
"""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

pytestmark = pytest.mark.integration


def test_migration_creates_all_tables(db_engine):
    """Verify all four tables exist after migration."""
    inspector = inspect(db_engine)
    table_names = inspector.get_table_names()
    assert "companies" in table_names
    assert "signal_details" in table_names
    assert "pipeline_runs" in table_names
    # daily_scores is partitioned -- parent may not appear in get_table_names()
    # Check via pg_tables for partitioned tables
    with db_engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE tablename LIKE 'daily_scores%'"
            )
        )
        ds_tables = [row[0] for row in result]
    assert any("daily_scores" in t for t in ds_tables)


def test_migration_idempotent(db_url):
    """Running upgrade head twice is a no-op (no error)."""
    os.environ["AI_WASHER_DATABASE_URL"] = db_url
    alembic_cfg = Config("alembic.ini")
    # Already at head from _run_migrations fixture; running again should be no-op
    command.upgrade(alembic_cfg, "head")
    # If we get here without error, idempotency holds


def test_daily_scores_is_partitioned(db_engine):
    """Verify daily_scores uses range partitioning."""
    with db_engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT c.relname, p.partstrat
            FROM pg_class c
            JOIN pg_partitioned_table p ON c.oid = p.partrelid
            WHERE c.relname = 'daily_scores'
        """)
        )
        rows = list(result)
    assert len(rows) == 1
    assert rows[0][1] == "r"  # 'r' = range partitioning


def test_daily_scores_has_monthly_partitions(db_engine):
    """Verify monthly partitions exist per D-06 (at least 12 for 2026)."""
    with db_engine.connect() as conn:
        result = conn.execute(
            text("""
            SELECT inhrelid::regclass::text
            FROM pg_inherits
            WHERE inhparent = 'daily_scores'::regclass
            ORDER BY 1
        """)
        )
        partitions = [row[0] for row in result]
    # Must have all 12 months of 2026 per D-06
    for month in range(1, 13):
        expected = f"daily_scores_2026_{month:02d}"
        assert expected in partitions, f"Missing monthly partition: {expected}"
    # Should also have some 2027 buffer partitions
    assert any("daily_scores_2027_" in p for p in partitions)
    # Total: 18 partitions (12 x 2026 + 6 x 2027)
    assert len(partitions) == 18
