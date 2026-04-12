"""Tests for DataValidator — DATA-05."""
from __future__ import annotations

from kalshi_backtest.ingestion.validator import DataValidator


def test_gap_detection_finds_missing_days(duckdb_con):
    """DATA-05: Gap detector identifies a missing day between two candle rows."""
    # Insert candles with a 3-day gap: Jan 1 → Jan 4 (missing Jan 2, Jan 3)
    duckdb_con.execute("""
        INSERT INTO candles (ticker, ts, close_price, ingested_at) VALUES
        ('TEST-001', '2025-01-01 00:00:00', 50, '2025-01-10 00:00:00'),
        ('TEST-001', '2025-01-04 00:00:00', 52, '2025-01-10 00:00:00')
    """)

    validator = DataValidator(duckdb_con)
    report = validator.validate_ticker("TEST-001")

    assert report.gap_count == 1, f"Expected 1 gap, got {report.gap_count}"
    assert report.gaps[0].gap_days == 3


def test_gap_detection_no_false_positives(duckdb_con):
    """DATA-05: Gap detector reports no gaps for a continuous daily candle series."""
    # Insert 5 consecutive daily candles
    for day in range(1, 6):
        duckdb_con.execute(
            "INSERT INTO candles (ticker, ts, close_price, ingested_at) VALUES (?, ?, ?, ?)",
            ["TEST-002", f"2025-02-0{day} 00:00:00", 45 + day, "2025-02-10 00:00:00"],
        )

    validator = DataValidator(duckdb_con)
    report = validator.validate_ticker("TEST-002")

    assert report.gap_count == 0, f"Expected 0 gaps, got {report.gap_count}: {report.gaps}"


def test_validation_report_structure(duckdb_con):
    """DATA-05: ValidationReport has coverage_pct, gap_count, and anomaly_count fields."""
    duckdb_con.execute("""
        INSERT INTO candles (ticker, ts, close_price, ingested_at) VALUES
        ('TEST-003', '2025-03-01 00:00:00', 60, '2025-03-15 00:00:00'),
        ('TEST-003', '2025-03-02 00:00:00', 62, '2025-03-15 00:00:00'),
        ('TEST-003', '2025-03-03 00:00:00', 58, '2025-03-15 00:00:00')
    """)

    validator = DataValidator(duckdb_con)
    report = validator.validate_ticker("TEST-003")

    assert hasattr(report, "coverage_pct")
    assert hasattr(report, "gap_count")
    assert hasattr(report, "anomaly_count")
    assert report.total_candles == 3
    assert isinstance(report.coverage_pct, float)
