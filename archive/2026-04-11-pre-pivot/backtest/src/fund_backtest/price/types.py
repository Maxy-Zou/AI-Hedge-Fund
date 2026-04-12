"""Pydantic type contracts for the price module.

Provides:
- price_to_cents: Convert float price to integer cents using round() (not int())
- PriceBar: A single daily OHLCV bar in cents, with yfinance factory method
- PriceAnomalyRecord: A flagged anomaly for a ticker/date
- DownloadSummary: Per-run statistics for the downloader
- CoverageReport: Coverage analysis with threshold comparison
"""
from __future__ import annotations

from datetime import date
from typing import Literal

import pandas as pd
from pydantic import BaseModel, field_validator


def price_to_cents(price: float) -> int:
    """Convert a float price to integer cents using round().

    Uses round(), not int(), to avoid floating-point truncation errors.
    Example: price_to_cents(183.73) == 18373, not 18372.

    Args:
        price: Price in dollars as a float (e.g. 183.73).

    Returns:
        Price in cents as an integer (e.g. 18373).
    """
    return round(price * 100)


class PriceBar(BaseModel):
    """A single daily OHLCV price bar for one ticker, all prices in cents.

    All OHLC values are stored as integers (cents) to avoid floating-point
    precision issues in financial calculations. Volume is stored as a raw integer.
    Ticker is normalized to uppercase on construction.

    Columns:
        ticker: Exchange symbol (e.g. "AAPL"), normalized to UPPER.
        bar_date: Trading date for this bar.
        open_cents: Opening price in cents.
        high_cents: Intraday high in cents.
        low_cents: Intraday low in cents.
        close_cents: Adjusted closing price in cents.
        volume: Shares traded.
    """

    ticker: str
    bar_date: date
    open_cents: int
    high_cents: int
    low_cents: int
    close_cents: int
    volume: int

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        """Normalize ticker to uppercase."""
        return v.upper()

    @classmethod
    def from_yfinance_row(
        cls,
        ticker: str,
        bar_date: date,
        row: pd.Series,
    ) -> PriceBar:
        """Build a PriceBar from a pandas Series row returned by yfinance.

        Uses price_to_cents() for OHLC values (round, not int).
        Volume is cast directly to int since it's already a whole number.

        Args:
            ticker: Exchange symbol (will be uppercased).
            bar_date: The trading date for this bar.
            row: A pandas Series with keys Open, High, Low, Close, Volume.

        Returns:
            A PriceBar with all prices converted to cents.
        """
        return cls(
            ticker=ticker,
            bar_date=bar_date,
            open_cents=price_to_cents(float(row["Open"])),
            high_cents=price_to_cents(float(row["High"])),
            low_cents=price_to_cents(float(row["Low"])),
            close_cents=price_to_cents(float(row["Close"])),
            volume=int(row["Volume"]),
        )


class PriceAnomalyRecord(BaseModel):
    """A flagged price anomaly for a specific ticker/date.

    Created when a daily return exceeds the configured anomaly threshold.
    anomaly_type is a closed enum to prevent typos in downstream consumers.

    Columns:
        ticker: Exchange symbol.
        bar_date: Date of the anomalous movement.
        anomaly_type: Classification — "return_spike_plus" (large up move)
                      or "return_spike_minus" (large down move).
        daily_return_pct: Calculated daily return percentage (e.g. 0.65 for +65%).
    """

    ticker: str
    bar_date: date
    anomaly_type: Literal["return_spike_plus", "return_spike_minus"]
    daily_return_pct: float


class DownloadSummary(BaseModel):
    """Per-run statistics from a price download operation.

    Returned by the downloader to describe what happened during a batch run.
    Downstream CLI uses this to report results to the operator.

    Fields:
        requested: Total number of tickers requested.
        successful: List of tickers that downloaded successfully.
        failed: List of tickers that failed (network error, no data, etc.).
        bars_inserted: Total number of OHLCV rows inserted into the database.
    """

    requested: int
    successful: list[str]
    failed: list[str]
    bars_inserted: int


class CoverageReport(BaseModel):
    """Coverage analysis comparing requested vs. successful ticker downloads.

    Computes coverage_pct and flags whether it's below the configured threshold.
    Used by the validator and CLI to alert operators when data coverage degrades.

    Fields:
        requested: Total tickers requested.
        successful: Count of tickers with complete data.
        failed: Count of tickers that failed.
        coverage_pct: successful / requested (1.0 if requested == 0).
        below_threshold: True when coverage_pct < threshold.
    """

    requested: int
    successful: int
    failed: int
    coverage_pct: float
    below_threshold: bool

    @classmethod
    def from_counts(
        cls,
        requested: list[str],
        successful: list[str],
        threshold: float = 0.95,
    ) -> CoverageReport:
        """Compute a CoverageReport from lists of ticker symbols.

        Args:
            requested: All tickers that were requested.
            successful: Tickers that completed successfully.
            threshold: Coverage fraction below which below_threshold=True.
                       Default 0.95 (95%).

        Returns:
            CoverageReport with computed coverage_pct and below_threshold flag.
        """
        n_requested = len(requested)
        n_successful = len(successful)
        n_failed = n_requested - n_successful

        if n_requested == 0:
            coverage_pct = 1.0
        else:
            coverage_pct = n_successful / n_requested

        return cls(
            requested=n_requested,
            successful=n_successful,
            failed=n_failed,
            coverage_pct=coverage_pct,
            below_threshold=coverage_pct < threshold,
        )
