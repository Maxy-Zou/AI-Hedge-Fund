"""Tests for data validator — DATA-05."""
import pytest


@pytest.mark.skip(reason="stub — implement in plan 04 after validator.py exists")
def test_gap_detection_finds_missing_days(duckdb_con):
    """DATA-05: Gap detector identifies a missing day between two candle rows."""
    pass


@pytest.mark.skip(reason="stub — implement in plan 04 after validator.py exists")
def test_gap_detection_no_false_positives(duckdb_con):
    """DATA-05: Gap detector reports no gaps for a continuous daily candle series."""
    pass


@pytest.mark.skip(reason="stub — implement in plan 04 after validator.py exists")
def test_validation_report_structure(duckdb_con):
    """DATA-05: ValidationReport has coverage_pct, gap_count, and anomaly_count fields."""
    pass
