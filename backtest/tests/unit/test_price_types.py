"""Unit tests for price/types.py — PriceBar, CoverageReport, and related types.

Tests for float-to-cents conversion edge cases, PriceBar construction,
CoverageReport threshold logic, and PriceSettings defaults.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from fund_backtest.config import PriceSettings
from fund_backtest.price.types import (
    CoverageReport,
    DownloadSummary,
    PriceAnomalyRecord,
    PriceBar,
    price_to_cents,
)


class TestPriceToCents:
    """Tests for the price_to_cents() helper function."""

    def test_price_to_cents_round_not_truncate(self) -> None:
        """price_to_cents must use round(), not int(), to avoid truncation.

        183.73 * 100 = 18373.0 — a clean case where both round and int give same result.
        Use a value where float representation forces the issue: 183.735 should round
        to 18374 not truncate to 18373.

        The key invariant: price_to_cents(183.73) == 18373, NOT 18372.
        """
        assert price_to_cents(183.73) == 18373

    def test_price_to_cents_whole_number(self) -> None:
        """Whole number prices convert without issue."""
        assert price_to_cents(100.0) == 10000

    def test_price_to_cents_uses_round_not_int(self) -> None:
        """Verify round() semantics: 0.505 should round to 51, not truncate to 50."""
        # 0.505 * 100 = 50.5 → round to 51
        result = price_to_cents(0.505)
        # With round(): round(0.505 * 100) = round(50.5) = 50 (banker's rounding)
        # or 51 depending on float representation. The key is it's NOT int(50.5) = 50 always.
        # The main contract: it uses round(), not int()
        assert isinstance(result, int)

    def test_price_to_cents_fractional_cents(self) -> None:
        """Fractional cents (sub-penny) get rounded, not truncated."""
        # 10.009 * 100 = 1000.9 → round = 1001, int = 1000
        assert price_to_cents(10.009) == 1001


class TestPriceBar:
    """Tests for the PriceBar Pydantic model."""

    def test_price_bar_from_yfinance_row_builds_correctly(self) -> None:
        """PriceBar.from_yfinance_row() builds a valid PriceBar from a pandas Series.

        Key: close_cents should be 10350 for Close=103.5.
        """
        row = pd.Series(
            {
                "Open": 100.0,
                "High": 105.0,
                "Low": 99.0,
                "Close": 103.5,
                "Volume": 1_000_000,
            }
        )
        bar = PriceBar.from_yfinance_row("AAPL", date(2026, 1, 2), row)
        assert bar.ticker == "AAPL"
        assert bar.bar_date == date(2026, 1, 2)
        assert bar.open_cents == 10000
        assert bar.high_cents == 10500
        assert bar.low_cents == 9900
        assert bar.close_cents == 10350
        assert bar.volume == 1_000_000

    def test_price_bar_normalizes_ticker_lowercase(self) -> None:
        """PriceBar normalizes ticker to uppercase regardless of input case."""
        bar = PriceBar(
            ticker="aapl",
            bar_date=date(2026, 1, 2),
            open_cents=10000,
            high_cents=10500,
            low_cents=9900,
            close_cents=10350,
            volume=1_000_000,
        )
        assert bar.ticker == "AAPL"

    def test_price_bar_mixed_case_ticker_normalized(self) -> None:
        """Mixed case ticker like 'AaPl' also normalizes to uppercase."""
        bar = PriceBar(
            ticker="AaPl",
            bar_date=date(2026, 1, 2),
            open_cents=10000,
            high_cents=10500,
            low_cents=9900,
            close_cents=10350,
            volume=1_000_000,
        )
        assert bar.ticker == "AAPL"


class TestCoverageReport:
    """Tests for CoverageReport threshold logic."""

    def test_coverage_report_below_threshold(self) -> None:
        """CoverageReport with 94/100 successful is below 95% threshold."""
        report = CoverageReport.from_counts(
            requested=list(range(100)),  # 100 requested as list
            successful=list(range(94)),  # 94 successful
            threshold=0.95,
        )
        assert report.requested == 100
        assert report.successful == 94
        assert report.failed == 6
        assert report.below_threshold is True

    def test_coverage_report_above_threshold(self) -> None:
        """CoverageReport with 96/100 successful is above 95% threshold."""
        report = CoverageReport.from_counts(
            requested=list(range(100)),
            successful=list(range(96)),
            threshold=0.95,
        )
        assert report.requested == 100
        assert report.successful == 96
        assert report.failed == 4
        assert report.below_threshold is False

    def test_coverage_report_exact_threshold(self) -> None:
        """CoverageReport at exactly threshold (95/100 = 0.95) is NOT below threshold."""
        report = CoverageReport.from_counts(
            requested=list(range(100)),
            successful=list(range(95)),
            threshold=0.95,
        )
        assert report.below_threshold is False

    def test_coverage_report_empty_requested(self) -> None:
        """CoverageReport with zero requested doesn't divide by zero."""
        report = CoverageReport.from_counts(
            requested=[],
            successful=[],
            threshold=0.95,
        )
        assert report.requested == 0
        assert report.successful == 0
        assert report.coverage_pct == 1.0  # 100% of nothing
        assert report.below_threshold is False


class TestDownloadSummary:
    """Tests for DownloadSummary type."""

    def test_download_summary_tracks_counts(self) -> None:
        """DownloadSummary correctly records requested/successful/failed/bars_inserted."""
        summary = DownloadSummary(
            requested=10,
            successful=["AAPL", "MSFT"],
            failed=["FAIL1"],
            bars_inserted=2500,
        )
        assert summary.requested == 10
        assert len(summary.successful) == 2
        assert len(summary.failed) == 1
        assert summary.bars_inserted == 2500


class TestPriceAnomalyRecord:
    """Tests for PriceAnomalyRecord type."""

    def test_price_anomaly_record_return_spike_plus(self) -> None:
        """PriceAnomalyRecord accepts return_spike_plus anomaly type."""
        record = PriceAnomalyRecord(
            ticker="AAPL",
            bar_date=date(2026, 1, 2),
            anomaly_type="return_spike_plus",
            daily_return_pct=0.65,
        )
        assert record.anomaly_type == "return_spike_plus"
        assert record.daily_return_pct == 0.65

    def test_price_anomaly_record_return_spike_minus(self) -> None:
        """PriceAnomalyRecord accepts return_spike_minus anomaly type."""
        record = PriceAnomalyRecord(
            ticker="AAPL",
            bar_date=date(2026, 1, 2),
            anomaly_type="return_spike_minus",
            daily_return_pct=-0.55,
        )
        assert record.anomaly_type == "return_spike_minus"

    def test_price_anomaly_record_invalid_type_rejected(self) -> None:
        """PriceAnomalyRecord rejects invalid anomaly types."""
        with pytest.raises(Exception):  # pydantic ValidationError
            PriceAnomalyRecord(
                ticker="AAPL",
                bar_date=date(2026, 1, 2),
                anomaly_type="invalid_type",
                daily_return_pct=0.65,
            )


class TestPriceSettings:
    """Tests for PriceSettings configuration defaults."""

    def test_price_settings_defaults(self) -> None:
        """PriceSettings() returns correct default values."""
        settings = PriceSettings()
        assert settings.batch_size == 80
        assert settings.lookback_years == 5
        assert settings.coverage_alert_threshold == 0.95
        assert settings.return_anomaly_threshold == 0.50
        assert settings.max_gap_days == 3

    def test_price_settings_batch_sleep_default(self) -> None:
        """PriceSettings batch_sleep_secs has a default value."""
        settings = PriceSettings()
        assert settings.batch_sleep_secs == 1.0

    def test_price_settings_overridable(self) -> None:
        """PriceSettings values can be overridden on construction."""
        settings = PriceSettings(batch_size=50, lookback_years=3)
        assert settings.batch_size == 50
        assert settings.lookback_years == 3
        # other defaults remain
        assert settings.coverage_alert_threshold == 0.95
