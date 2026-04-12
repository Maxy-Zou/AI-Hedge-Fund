"""Equity price client with yfinance primary and Tiingo fallback.

Downloads OHLCV price data, converts all monetary values to integer cents,
and provides a unified interface regardless of data source. The fallback
pattern handles yfinance fragility -- if yfinance fails or returns empty
data, Tiingo is used automatically.

Threat mitigations:
- T-02-10: tenacity retry with exponential backoff on yfinance
- T-02-11: Tiingo API key not logged, passed only to authenticated requests
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential
from tiingo import TiingoClient

logger = logging.getLogger(__name__)


class PriceDownloadError(Exception):
    """Raised when all price data sources fail."""


def _dollars_to_cents(value: float) -> int:
    """Convert a dollar float to integer cents.

    Uses round() to handle floating-point imprecision before int conversion.

    Args:
        value: Dollar amount as float (e.g., 150.50).

    Returns:
        Integer cents (e.g., 15050).
    """
    return int(round(value * 100))


class PriceClient:
    """Equity price downloader with yfinance + Tiingo fallback.

    All prices are returned as integer cents to avoid floating-point
    errors in financial calculations. The source field tracks data
    provenance for auditing.

    Args:
        tiingo_api_key: Optional Tiingo API key for fallback. Empty
            string means Tiingo fallback is disabled.
    """

    def __init__(self, tiingo_api_key: str = "") -> None:
        self._tiingo_api_key = tiingo_api_key

    def download(self, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        """Download price data, trying yfinance first then Tiingo.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL").
            start_date: First date to fetch (inclusive).
            end_date: Last date to fetch (inclusive).

        Returns:
            List of price dicts with cents values.

        Raises:
            PriceDownloadError: When both sources fail or return no data.
        """
        yf_error: str | None = None

        # Try yfinance first
        try:
            result = self.download_yfinance(ticker, start_date, end_date)
            if result:
                return result
            yf_error = "yfinance returned empty DataFrame"
            logger.warning("yfinance returned empty data for %s, trying Tiingo", ticker)
        except Exception as exc:
            yf_error = str(exc)
            logger.warning("yfinance failed for %s: %s, trying Tiingo", ticker, exc)

        # Fall back to Tiingo
        try:
            return self.download_tiingo(ticker, start_date, end_date)
        except Exception as tiingo_exc:
            msg = (
                f"Price download failed for {ticker}: both sources failed. "
                f"yfinance: {yf_error}. Tiingo: {tiingo_exc}"
            )
            raise PriceDownloadError(msg) from tiingo_exc

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def download_yfinance(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """Download price data from yfinance.

        Args:
            ticker: Stock ticker symbol.
            start_date: First date (inclusive).
            end_date: Last date (inclusive).

        Returns:
            List of price dicts with cents values and source="yfinance".
        """
        df = yf.download(
            ticker,
            start=start_date.isoformat(),
            end=(end_date + pd.tseries.offsets.BDay(1)).date().isoformat(),
            auto_adjust=False,
            progress=False,
        )
        if df.empty:
            return []

        return self._df_to_price_dicts(df, source="yfinance")

    def download_tiingo(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """Download price data from Tiingo.

        Args:
            ticker: Stock ticker symbol.
            start_date: First date (inclusive).
            end_date: Last date (inclusive).

        Returns:
            List of price dicts with cents values and source="tiingo".

        Raises:
            PriceDownloadError: If Tiingo API key is not configured.
        """
        if not self._tiingo_api_key:
            msg = "Tiingo API key not configured -- cannot use Tiingo fallback"
            raise PriceDownloadError(msg)

        client = TiingoClient({"api_key": self._tiingo_api_key})
        raw = client.get_ticker_price(
            ticker,
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            frequency="daily",
        )

        return self._tiingo_to_price_dicts(raw)

    def _df_to_price_dicts(self, df: pd.DataFrame, source: str) -> list[dict[str, Any]]:
        """Convert a pandas DataFrame to list of price dicts in cents.

        Handles both single-ticker and multi-ticker yfinance DataFrames.

        Args:
            df: DataFrame with OHLCV columns and DatetimeIndex.
            source: Data source identifier (e.g., "yfinance").

        Returns:
            List of price dicts with all monetary values as int cents.
        """
        # Handle multi-level columns from yfinance (ticker as second level)
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(level=1, axis=1)

        results: list[dict[str, Any]] = []
        for idx, row in df.iterrows():
            trade_date = idx.date() if hasattr(idx, "date") else idx
            results.append(
                {
                    "trade_date": trade_date,
                    "open_cents": _dollars_to_cents(row["Open"]),
                    "high_cents": _dollars_to_cents(row["High"]),
                    "low_cents": _dollars_to_cents(row["Low"]),
                    "close_cents": _dollars_to_cents(row["Close"]),
                    "adj_close_cents": _dollars_to_cents(row["Adj Close"]),
                    "volume": int(row["Volume"]),
                    "source": source,
                }
            )

        return results

    def _tiingo_to_price_dicts(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert Tiingo API response to list of price dicts in cents.

        Args:
            raw: List of dicts from TiingoClient.get_ticker_price.

        Returns:
            List of price dicts with all monetary values as int cents.
        """
        results: list[dict[str, Any]] = []
        for item in raw:
            raw_date = item["date"]
            if isinstance(raw_date, str):
                trade_date = date.fromisoformat(raw_date[:10])
            else:
                trade_date = raw_date.date() if hasattr(raw_date, "date") else raw_date

            results.append(
                {
                    "trade_date": trade_date,
                    "open_cents": _dollars_to_cents(item["open"]),
                    "high_cents": _dollars_to_cents(item["high"]),
                    "low_cents": _dollars_to_cents(item["low"]),
                    "close_cents": _dollars_to_cents(item["close"]),
                    "adj_close_cents": _dollars_to_cents(item["adjClose"]),
                    "volume": int(item["volume"]),
                    "source": "tiingo",
                }
            )

        return results
