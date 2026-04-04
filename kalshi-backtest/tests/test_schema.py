"""Tests for DuckDB schema — DATA-03 (lookahead safety) and DATA-06 (UTC timestamps)."""
import pytest


@pytest.mark.skip(reason="stub — implement in plan 02 after schema.py exists")
def test_lookahead_safe_schema(duckdb_con):
    """DATA-03: result column is NULL for unsettled markets; only set after status=settled."""
    pass


@pytest.mark.skip(reason="stub — implement in plan 02 after schema.py exists")
def test_dst_timestamp_roundtrip(duckdb_con):
    """DATA-06: Timestamps stored as naive UTC survive DST transition without off-by-1h error."""
    pass


@pytest.mark.skip(reason="stub — implement in plan 02 after schema.py exists")
def test_candle_insert_idempotent(duckdb_con):
    """DATA-03/DATA-04: Inserting same (ticker, ts) row twice stores only one row."""
    pass
