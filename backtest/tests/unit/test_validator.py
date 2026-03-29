"""Unit tests for price/validator.py — anomaly detection, gap detection, and coverage.

Tests are written TDD-first (RED phase). They validate:
- detect_return_anomalies flags spikes above ±50% threshold
- detect_return_anomalies skips first bar (NaN pct_change) and below-threshold moves
- detect_gaps flags gaps of >3 business days, ignores gaps of ≤3 business days
- compute_coverage / CoverageReport.from_counts() correctly computes below_threshold flag
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from fund_backtest.price.types import CoverageReport, PriceAnomalyRecord
from fund_backtest.price.validator import compute_coverage, detect_gaps, detect_return_anomalies


def _make_close_df(dates: list[date], close_prices: list[float]) -> pd.DataFrame:
    """Build a minimal DataFrame with a Close column on a DatetimeIndex.

    Args:
        dates: List of dates.
        close_prices: Corresponding Close prices.

    Returns:
        DataFrame with 'Close' column indexed by DatetimeIndex.
    """
    return pd.DataFrame(
        {"Close": close_prices},
        index=pd.DatetimeIndex([pd.Timestamp(d) for d in dates]),
    )


def _business_dates(start: date, count: int) -> list[date]:
    """Generate `count` consecutive business dates starting from `start`."""
    bdays = pd.bdate_range(start=start, periods=count).date.tolist()
    return bdays


class TestDetectReturnAnomalies:
    """Tests for detect_return_anomalies()."""

    def test_detect_return_anomalies_flags_spike_plus(self) -> None:
        """Close=[100, 160] → anomaly_type='return_spike_plus', daily_return_pct≈60.0."""
        dates = _business_dates(date(2024, 1, 2), 2)
        df = _make_close_df(dates, [100.0, 160.0])
        result = detect_return_anomalies("AAPL", df)
        assert len(result) == 1
        anomaly = result[0]
        assert anomaly.ticker == "AAPL"
        assert anomaly.anomaly_type == "return_spike_plus"
        assert abs(anomaly.daily_return_pct - 60.0) < 0.01

    def test_detect_return_anomalies_flags_spike_minus(self) -> None:
        """Close=[100, 45] → anomaly_type='return_spike_minus', daily_return_pct≈-55.0."""
        dates = _business_dates(date(2024, 1, 2), 2)
        df = _make_close_df(dates, [100.0, 45.0])
        result = detect_return_anomalies("TSLA", df)
        assert len(result) == 1
        anomaly = result[0]
        assert anomaly.ticker == "TSLA"
        assert anomaly.anomaly_type == "return_spike_minus"
        assert abs(anomaly.daily_return_pct - (-55.0)) < 0.01

    def test_detect_return_anomalies_no_spike_below_threshold(self) -> None:
        """Close=[100, 140] (40% move) is below the 50% threshold → empty list."""
        dates = _business_dates(date(2024, 1, 2), 2)
        df = _make_close_df(dates, [100.0, 140.0])
        result = detect_return_anomalies("MSFT", df)
        assert result == [], f"Expected no anomalies for 40% move, got {result}"

    def test_detect_return_anomalies_first_bar_no_pct_change(self) -> None:
        """First bar has NaN pct_change and must be skipped — only 1 anomaly for [100, 160]."""
        dates = _business_dates(date(2024, 1, 2), 2)
        df = _make_close_df(dates, [100.0, 160.0])
        result = detect_return_anomalies("AAPL", df)
        # There are only 2 bars. The first bar has NaN pct_change (no prior bar),
        # so at most 1 anomaly can be detected (the second bar showing +60% move).
        assert len(result) == 1
        assert result[0].bar_date == dates[1]

    def test_detect_return_anomalies_returns_price_anomaly_records(self) -> None:
        """Result items must be PriceAnomalyRecord instances, not raw dicts."""
        dates = _business_dates(date(2024, 1, 2), 2)
        df = _make_close_df(dates, [100.0, 200.0])
        result = detect_return_anomalies("GOOG", df)
        assert len(result) == 1
        assert isinstance(result[0], PriceAnomalyRecord)

    def test_detect_return_anomalies_custom_threshold(self) -> None:
        """With threshold=0.30, a 35% move should be flagged."""
        dates = _business_dates(date(2024, 1, 2), 2)
        df = _make_close_df(dates, [100.0, 135.0])
        result = detect_return_anomalies("NVDA", df, threshold=0.30)
        assert len(result) == 1
        assert result[0].anomaly_type == "return_spike_plus"


class TestDetectGaps:
    """Tests for detect_gaps()."""

    def test_detect_gaps_flags_gap_over_3_days(self) -> None:
        """A gap of 5 business days between two dates must be flagged."""
        # Jan 2 (Wed) to Jan 10 (Thu) has 5 business days strictly between them
        # (Jan 3 Thu, Jan 6 Mon, Jan 7 Tue, Jan 8 Wed, Jan 9 Thu)
        dates = [date(2024, 1, 2), date(2024, 1, 10)]
        gaps = detect_gaps("AAPL", dates)
        assert len(gaps) == 1
        gap = gaps[0]
        assert gap["ticker"] == "AAPL"
        assert gap["gap_start"] == date(2024, 1, 2)
        assert gap["gap_end"] == date(2024, 1, 10)
        assert gap["missing_business_days"] > 3

    def test_detect_gaps_ignores_gap_of_3_or_fewer_days(self) -> None:
        """A gap of ≤3 business days (holiday/long weekend) must NOT be flagged."""
        # Jan 2 (Tue) to Jan 5 (Fri): strictly between = Jan 3, Jan 4 = 2 business days
        dates = [date(2024, 1, 2), date(2024, 1, 5)]
        gaps = detect_gaps("MSFT", dates)
        assert gaps == [], f"Expected no gaps for 2-business-day gap, got {gaps}"

    def test_detect_gaps_ignores_adjacent_business_days(self) -> None:
        """Two consecutive business days have 0 missing days → no gap."""
        dates = _business_dates(date(2024, 1, 2), 3)
        gaps = detect_gaps("TSLA", dates)
        assert gaps == []

    def test_detect_gaps_empty_list(self) -> None:
        """Empty date list should return empty gaps list."""
        gaps = detect_gaps("AAPL", [])
        assert gaps == []

    def test_detect_gaps_single_date(self) -> None:
        """Single date cannot have a gap — should return empty."""
        gaps = detect_gaps("AAPL", [date(2024, 1, 2)])
        assert gaps == []

    def test_detect_gaps_multiple_gaps(self) -> None:
        """Two separate gaps in the sequence both get flagged."""
        # Two gaps: one around Jan 10 and one around Jan 20
        dates = [
            date(2024, 1, 2),
            date(2024, 1, 10),   # 5 business day gap from Jan 2
            date(2024, 1, 11),
            date(2024, 1, 22),   # further big gap
        ]
        gaps = detect_gaps("GOOG", dates)
        assert len(gaps) >= 2


class TestComputeCoverage:
    """Tests for compute_coverage() and CoverageReport.from_counts()."""

    def test_compute_coverage_below_threshold(self) -> None:
        """94 successful / 100 requested → below_threshold=True, coverage_pct==94.0%."""
        requested = [f"T{i:03d}" for i in range(100)]
        successful = requested[:94]
        report = compute_coverage(requested, successful)
        assert report.below_threshold is True
        assert abs(report.coverage_pct - 0.94) < 1e-6
        assert report.requested == 100
        assert report.successful == 94
        assert report.failed == 6

    def test_compute_coverage_above_threshold(self) -> None:
        """96 successful / 100 requested → below_threshold=False."""
        requested = [f"T{i:03d}" for i in range(100)]
        successful = requested[:96]
        report = compute_coverage(requested, successful)
        assert report.below_threshold is False
        assert abs(report.coverage_pct - 0.96) < 1e-6

    def test_coverage_alert_below_threshold(self) -> None:
        """CoverageReport.from_counts() integration: same behavior via the classmethod."""
        requested = [f"T{i:03d}" for i in range(100)]
        successful = requested[:94]
        report = CoverageReport.from_counts(requested=requested, successful=successful)
        assert report.below_threshold is True
        assert report.requested == 100

    def test_compute_coverage_exactly_at_threshold(self) -> None:
        """95 / 100 = exactly 0.95 → below_threshold=False (not strictly less than)."""
        requested = [f"T{i:03d}" for i in range(100)]
        successful = requested[:95]
        report = compute_coverage(requested, successful)
        # coverage_pct == 0.95, threshold == 0.95: below_threshold is (0.95 < 0.95) = False
        assert report.below_threshold is False

    def test_compute_coverage_empty_requested(self) -> None:
        """Empty requested list → coverage_pct=1.0, below_threshold=False."""
        report = compute_coverage([], [])
        assert report.coverage_pct == 1.0
        assert report.below_threshold is False
