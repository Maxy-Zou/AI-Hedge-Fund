"""FRED API client for macroeconomic indicator retrieval.

Wraps the fredapi SDK with retry logic, temporal filtering, and
computed indicators (CPI YoY, GDP growth). API keys are loaded
from AppSettings and never logged.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import structlog
from fredapi import Fred
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


FRED_SERIES: dict[str, dict[str, str]] = {
    "fed_funds_rate": {
        "series_id": "FEDFUNDS",
        "description": "Effective Federal Funds Rate",
        "frequency": "monthly",
    },
    "cpi": {
        "series_id": "CPIAUCSL",
        "description": "Consumer Price Index for All Urban Consumers (seasonally adjusted)",
        "frequency": "monthly",
    },
    "gdp": {
        "series_id": "GDP",
        "description": "Gross Domestic Product (nominal, seasonally adjusted annual rate)",
        "frequency": "quarterly",
    },
    "real_gdp": {
        "series_id": "GDPC1",
        "description": "Real Gross Domestic Product (chained 2017 dollars, SAAR)",
        "frequency": "quarterly",
    },
    "yield_curve_spread": {
        "series_id": "T10Y2Y",
        "description": "10-Year Treasury Constant Maturity Minus 2-Year Treasury",
        "frequency": "daily",
    },
    "treasury_10y": {
        "series_id": "DGS10",
        "description": "10-Year Treasury Constant Maturity Rate",
        "frequency": "daily",
    },
    "treasury_2y": {
        "series_id": "DGS2",
        "description": "2-Year Treasury Constant Maturity Rate",
        "frequency": "daily",
    },
}


class FredClient:
    """Client for FRED macroeconomic data API.

    Args:
        api_key: FRED API key. Must be non-empty.

    Raises:
        ValueError: If api_key is empty.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            msg = "api_key is required -- configure fred_api_key in .env"
            raise ValueError(msg)
        self._fred = Fred(api_key=api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    def get_series(
        self,
        series_id: str,
        observation_start: date | None = None,
        observation_end: date | None = None,
    ) -> pd.Series:
        """Retrieve a FRED time series.

        Args:
            series_id: FRED series identifier (e.g., "FEDFUNDS").
            observation_start: Start date for observations (inclusive).
            observation_end: End date for observations (inclusive).

        Returns:
            Pandas Series with DatetimeIndex containing observation values.
        """
        kwargs: dict[str, Any] = {}
        if observation_start is not None:
            kwargs["observation_start"] = str(observation_start)
        if observation_end is not None:
            kwargs["observation_end"] = str(observation_end)

        return self._fred.get_series(series_id, **kwargs)

    def get_latest_values(self, as_of_date: date) -> dict[str, float | None]:
        """Get the latest value for each FRED series as of a given date.

        For each series in FRED_SERIES, retrieves observations up to
        as_of_date and returns the most recent non-NaN value.

        Args:
            as_of_date: Temporal cutoff date. Observations after this
                date are excluded.

        Returns:
            Dict mapping series name to its latest value, or None if
            no data is available.
        """
        result: dict[str, float | None] = {}

        for name, config in FRED_SERIES.items():
            try:
                series = self.get_series(
                    config["series_id"],
                    observation_end=as_of_date,
                )
                # Filter to observations <= as_of_date (belt and suspenders)
                if not series.empty:
                    cutoff = pd.Timestamp(as_of_date)
                    filtered = series[series.index <= cutoff]
                    filtered = filtered.dropna()
                    result[name] = float(filtered.iloc[-1]) if not filtered.empty else None
                else:
                    result[name] = None
            except Exception:
                logger.warning(
                    "fred_series_fetch_failed",
                    series_id=config["series_id"],
                    series_name=name,
                )
                result[name] = None

        return result

    def compute_cpi_yoy(self, as_of_date: date) -> float | None:
        """Compute CPI Year-over-Year percentage change.

        Compares the latest CPI observation to the observation from
        12 months prior.

        Args:
            as_of_date: Temporal cutoff date.

        Returns:
            YoY percentage change (e.g., 3.2 for 3.2%), or None if
            insufficient data.
        """
        try:
            series = self.get_series(
                FRED_SERIES["cpi"]["series_id"],
                observation_end=as_of_date,
            )
        except Exception:
            logger.warning("fred_cpi_fetch_failed")
            return None

        if series.empty:
            return None

        series = series.dropna()
        if len(series) < 2:
            return None

        current = series.iloc[-1]
        current_date = series.index[-1]

        # Find observation closest to 12 months prior
        target_date = current_date - pd.DateOffset(months=12)
        prior_candidates = series[series.index <= target_date]

        if prior_candidates.empty:
            return None

        prior = prior_candidates.iloc[-1]

        if prior == 0:
            return None

        return ((current - prior) / prior) * 100

    def compute_gdp_growth(self, as_of_date: date) -> float | None:
        """Compute quarter-over-quarter annualized real GDP growth.

        Uses the real GDP (GDPC1) series. Compares the latest quarter
        to the prior quarter and annualizes the growth rate.

        Args:
            as_of_date: Temporal cutoff date.

        Returns:
            Annualized QoQ growth percentage (e.g., 2.4 for 2.4%),
            or None if insufficient data.
        """
        try:
            series = self.get_series(
                FRED_SERIES["real_gdp"]["series_id"],
                observation_end=as_of_date,
            )
        except Exception:
            logger.warning("fred_gdp_fetch_failed")
            return None

        if series.empty:
            return None

        series = series.dropna()
        if len(series) < 2:
            return None

        current = series.iloc[-1]
        prior = series.iloc[-2]

        if prior == 0:
            return None

        qoq_change = (current - prior) / prior
        annualized = ((1 + qoq_change) ** 4 - 1) * 100

        return annualized
