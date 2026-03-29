"""Validation functions for OHLCV price data.

Public API:
    detect_return_anomalies(ticker, bars_df, threshold) -> list[PriceAnomalyRecord]
    detect_gaps(ticker, actual_dates, max_gap_days) -> list[dict]
    compute_coverage(requested, successful, threshold) -> CoverageReport
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import structlog

from fund_backtest.price.types import CoverageReport, PriceAnomalyRecord

log = structlog.get_logger(__name__)


def detect_return_anomalies(
    ticker: str,
    bars_df: pd.DataFrame,
    threshold: float = 0.50,
) -> list[PriceAnomalyRecord]:
    """Detect bars where |daily return| exceeds threshold.

    The first bar always has NaN pct_change (no prior bar) and is skipped.
    A return of +50% (0.50) exactly is below the threshold — only strictly
    greater than threshold values are flagged.

    Args:
        ticker: Exchange symbol for the data.
        bars_df: DataFrame with at least a 'Close' column and DatetimeIndex.
        threshold: Fraction above which the absolute return is anomalous.
                   Default 0.50 (50%).

    Returns:
        List of PriceAnomalyRecord for each anomalous bar, in date order.
    """
    returns = bars_df["Close"].pct_change()
    anomaly_returns = returns[returns.abs() > threshold].dropna()
    result = []
    for bar_date, ret in anomaly_returns.items():
        bar_date_val = bar_date.date() if hasattr(bar_date, "date") else bar_date
        result.append(
            PriceAnomalyRecord(
                ticker=ticker,
                bar_date=bar_date_val,
                anomaly_type="return_spike_plus" if ret > 0 else "return_spike_minus",
                daily_return_pct=round(float(ret) * 100, 4),
            )
        )
    return result


def detect_gaps(
    ticker: str,
    actual_dates: list[date],
    max_gap_days: int = 3,
) -> list[dict]:
    """Detect consecutive business-day gaps exceeding max_gap_days.

    Gaps of <= max_gap_days are expected (holidays, long weekends) and ignored.
    Only gaps strictly > max_gap_days are flagged.

    The gap size is computed as the number of business days strictly between
    two consecutive dates using pd.bdate_range(inclusive="neither"). This
    count excludes the start and end dates themselves.

    Args:
        ticker: Exchange symbol for logging and result annotation.
        actual_dates: List of dates that actually have price bars.
        max_gap_days: Maximum allowed gap in business days (default 3).
                      Gaps with exactly max_gap_days missing are allowed.

    Returns:
        List of dicts with keys: ticker, gap_start, gap_end, missing_business_days.
    """
    if len(actual_dates) < 2:
        return []
    sorted_dates = sorted(actual_dates)
    gaps = []
    for i in range(1, len(sorted_dates)):
        prev, curr = sorted_dates[i - 1], sorted_dates[i]
        # Business days strictly BETWEEN prev and curr (exclusive of both endpoints)
        expected = pd.bdate_range(start=prev, end=curr, inclusive="neither")
        gap_size = len(expected)
        if gap_size > max_gap_days:
            gaps.append(
                {
                    "ticker": ticker,
                    "gap_start": prev,
                    "gap_end": curr,
                    "missing_business_days": gap_size,
                }
            )
            log.warning(
                "price_gap_detected",
                ticker=ticker,
                gap_start=str(prev),
                gap_end=str(curr),
                days=gap_size,
            )
    return gaps


def compute_coverage(
    requested: list[str],
    successful: list[str],
    threshold: float = 0.95,
) -> CoverageReport:
    """Compute coverage ratio and alert flag.

    Delegates to CoverageReport.from_counts() to keep logic in one place.

    Args:
        requested: All tickers that were requested.
        successful: Tickers that completed successfully.
        threshold: Coverage fraction below which below_threshold=True.
                   Default 0.95 (95%).

    Returns:
        CoverageReport with coverage_pct and below_threshold flag.
    """
    return CoverageReport.from_counts(
        requested=requested,
        successful=successful,
        threshold=threshold,
    )
