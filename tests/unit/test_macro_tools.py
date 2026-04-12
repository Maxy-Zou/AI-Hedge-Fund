"""Tests for FRED macro data client and macro context tools.

Tests cover:
- FredClient initialization and API key validation
- Series retrieval with temporal filtering
- Latest values extraction across all FRED series
- CPI YoY computation from 12-month-ago observation
- GDP growth computation from prior quarter
- get_macro_context temporal enforcement (as_of_date)
- NL summary generation via format_macro_summary
- DB caching of observations to MacroIndicator model
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings
from ai_hedge_fund.data.clients.fred_client import FRED_SERIES, FredClient
from ai_hedge_fund.data.tools.macro_tools import get_macro_context
from ai_hedge_fund.db.models import MacroIndicator


# ---------------------------------------------------------------------------
# Sample FRED data
# ---------------------------------------------------------------------------

def _make_series(data: dict[str, float]) -> pd.Series:
    """Build a pandas Series with DatetimeIndex from {date_str: value} dict."""
    index = pd.DatetimeIndex([pd.Timestamp(d) for d in data])
    return pd.Series(list(data.values()), index=index)


SAMPLE_FED_FUNDS = _make_series({
    "2023-10-01": 5.33,
    "2023-11-01": 5.33,
    "2023-12-01": 5.33,
    "2024-01-01": 5.33,
})

SAMPLE_CPI = _make_series({
    "2023-01-01": 300.5,  # 12 months prior
    "2023-06-01": 304.1,
    "2023-12-01": 308.7,
    "2024-01-01": 310.2,  # Current month
})

SAMPLE_GDP = _make_series({
    "2023-04-01": 22038.2,  # Q2 2023
    "2023-07-01": 22340.5,  # Q3 2023
    "2023-10-01": 22598.1,  # Q4 2023
    "2024-01-01": 22801.0,  # Q1 2024
})

SAMPLE_REAL_GDP = _make_series({
    "2023-04-01": 20230.0,  # Q2 2023
    "2023-07-01": 20380.0,  # Q3 2023
    "2023-10-01": 20520.0,  # Q4 2023
    "2024-01-01": 20640.0,  # Q1 2024
})

SAMPLE_YIELD_SPREAD = _make_series({
    "2023-12-01": -0.45,
    "2023-12-15": -0.42,
    "2024-01-02": -0.38,
    "2024-01-15": -0.35,
})

SAMPLE_TREASURY_10Y = _make_series({
    "2023-12-01": 4.25,
    "2023-12-15": 3.98,
    "2024-01-02": 4.05,
    "2024-01-15": 4.12,
})

SAMPLE_TREASURY_2Y = _make_series({
    "2023-12-01": 4.70,
    "2023-12-15": 4.40,
    "2024-01-02": 4.43,
    "2024-01-15": 4.47,
})


# ---------------------------------------------------------------------------
# FRED_SERIES configuration tests
# ---------------------------------------------------------------------------


class TestFredSeriesConfig:
    """Tests for the FRED_SERIES configuration dict."""

    def test_contains_required_series(self) -> None:
        """FRED_SERIES contains all 7 required series."""
        expected_keys = {
            "fed_funds_rate",
            "cpi",
            "gdp",
            "real_gdp",
            "yield_curve_spread",
            "treasury_10y",
            "treasury_2y",
        }
        assert set(FRED_SERIES.keys()) == expected_keys

    def test_series_ids_are_correct(self) -> None:
        """FRED series IDs match the official FRED identifiers."""
        assert FRED_SERIES["fed_funds_rate"]["series_id"] == "FEDFUNDS"
        assert FRED_SERIES["cpi"]["series_id"] == "CPIAUCSL"
        assert FRED_SERIES["gdp"]["series_id"] == "GDP"
        assert FRED_SERIES["real_gdp"]["series_id"] == "GDPC1"
        assert FRED_SERIES["yield_curve_spread"]["series_id"] == "T10Y2Y"
        assert FRED_SERIES["treasury_10y"]["series_id"] == "DGS10"
        assert FRED_SERIES["treasury_2y"]["series_id"] == "DGS2"

    def test_each_series_has_description(self) -> None:
        """Each FRED series entry has a description."""
        for name, config in FRED_SERIES.items():
            assert "description" in config, f"Missing description for {name}"
            assert len(config["description"]) > 0

    def test_each_series_has_frequency(self) -> None:
        """Each FRED series entry has a frequency."""
        for name, config in FRED_SERIES.items():
            assert "frequency" in config, f"Missing frequency for {name}"


# ---------------------------------------------------------------------------
# FredClient tests
# ---------------------------------------------------------------------------


class TestFredClient:
    """Tests for the FredClient wrapper."""

    def test_raises_on_empty_api_key(self) -> None:
        """FredClient raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key"):
            FredClient(api_key="")

    @patch("ai_hedge_fund.data.clients.fred_client.Fred")
    def test_get_series_returns_pandas_series(self, mock_fred_cls: MagicMock) -> None:
        """get_series returns a pandas Series filtered by observation_end."""
        mock_instance = MagicMock()
        mock_instance.get_series.return_value = SAMPLE_FED_FUNDS
        mock_fred_cls.return_value = mock_instance

        client = FredClient(api_key="test-key")
        result = client.get_series("FEDFUNDS", observation_end=date(2024, 1, 15))

        assert isinstance(result, pd.Series)
        mock_instance.get_series.assert_called_once()

    @patch("ai_hedge_fund.data.clients.fred_client.Fred")
    def test_get_latest_values_returns_dict(self, mock_fred_cls: MagicMock) -> None:
        """get_latest_values returns dict of {series_name: latest_value}."""
        mock_instance = MagicMock()

        def side_effect(series_id, **kwargs):
            mapping = {
                "FEDFUNDS": SAMPLE_FED_FUNDS,
                "CPIAUCSL": SAMPLE_CPI,
                "GDP": SAMPLE_GDP,
                "GDPC1": SAMPLE_REAL_GDP,
                "T10Y2Y": SAMPLE_YIELD_SPREAD,
                "DGS10": SAMPLE_TREASURY_10Y,
                "DGS2": SAMPLE_TREASURY_2Y,
            }
            return mapping.get(series_id, pd.Series(dtype=float))

        mock_instance.get_series.side_effect = side_effect
        mock_fred_cls.return_value = mock_instance

        client = FredClient(api_key="test-key")
        result = client.get_latest_values(as_of_date=date(2024, 1, 15))

        assert isinstance(result, dict)
        assert "fed_funds_rate" in result
        assert "cpi" in result
        assert "yield_curve_spread" in result
        assert "treasury_10y" in result

    @patch("ai_hedge_fund.data.clients.fred_client.Fred")
    def test_get_latest_values_excludes_future(self, mock_fred_cls: MagicMock) -> None:
        """get_latest_values only includes observations <= as_of_date."""
        mock_instance = MagicMock()
        # Return series with a value after as_of_date
        future_series = _make_series({
            "2024-01-01": 5.33,
            "2024-02-01": 5.50,  # After as_of_date of Jan 15
        })
        mock_instance.get_series.return_value = future_series
        mock_fred_cls.return_value = mock_instance

        client = FredClient(api_key="test-key")
        result = client.get_latest_values(as_of_date=date(2024, 1, 15))

        # Should use 5.33 (Jan 1), not 5.50 (Feb 1)
        assert result["fed_funds_rate"] == pytest.approx(5.33)

    @patch("ai_hedge_fund.data.clients.fred_client.Fred")
    def test_handles_missing_series(self, mock_fred_cls: MagicMock) -> None:
        """get_latest_values returns None for a series that has no data."""
        mock_instance = MagicMock()
        mock_instance.get_series.return_value = pd.Series(dtype=float)
        mock_fred_cls.return_value = mock_instance

        client = FredClient(api_key="test-key")
        result = client.get_latest_values(as_of_date=date(2024, 1, 15))

        # All series should be None since the mock returns empty
        for value in result.values():
            assert value is None

    @patch("ai_hedge_fund.data.clients.fred_client.Fred")
    def test_compute_cpi_yoy(self, mock_fred_cls: MagicMock) -> None:
        """CPI YoY computed correctly from 12-month-ago vs current observation."""
        mock_instance = MagicMock()
        mock_instance.get_series.return_value = SAMPLE_CPI
        mock_fred_cls.return_value = mock_instance

        client = FredClient(api_key="test-key")
        result = client.compute_cpi_yoy(as_of_date=date(2024, 1, 31))

        # YoY = (310.2 - 300.5) / 300.5 * 100 = 3.228...%
        assert result is not None
        assert result == pytest.approx(3.228, abs=0.01)

    @patch("ai_hedge_fund.data.clients.fred_client.Fred")
    def test_compute_gdp_growth(self, mock_fred_cls: MagicMock) -> None:
        """GDP growth computed correctly from prior quarter (QoQ annualized)."""
        mock_instance = MagicMock()
        mock_instance.get_series.return_value = SAMPLE_REAL_GDP
        mock_fred_cls.return_value = mock_instance

        client = FredClient(api_key="test-key")
        result = client.compute_gdp_growth(as_of_date=date(2024, 1, 31))

        # QoQ change: (20640 - 20520) / 20520 = 0.00585...
        # Annualized: ((1 + 0.00585)^4 - 1) * 100 = ~2.36%
        assert result is not None
        assert result == pytest.approx(2.36, abs=0.1)

    @patch("ai_hedge_fund.data.clients.fred_client.Fred")
    def test_compute_cpi_yoy_handles_missing_data(self, mock_fred_cls: MagicMock) -> None:
        """CPI YoY returns None when insufficient historical data."""
        mock_instance = MagicMock()
        # Only one data point -- not enough for YoY
        mock_instance.get_series.return_value = _make_series({"2024-01-01": 310.2})
        mock_fred_cls.return_value = mock_instance

        client = FredClient(api_key="test-key")
        result = client.compute_cpi_yoy(as_of_date=date(2024, 1, 31))

        assert result is None

    @patch("ai_hedge_fund.data.clients.fred_client.Fred")
    def test_compute_gdp_growth_handles_missing_data(self, mock_fred_cls: MagicMock) -> None:
        """GDP growth returns None when insufficient quarterly data."""
        mock_instance = MagicMock()
        mock_instance.get_series.return_value = _make_series({"2024-01-01": 22801.0})
        mock_fred_cls.return_value = mock_instance

        client = FredClient(api_key="test-key")
        result = client.compute_gdp_growth(as_of_date=date(2024, 1, 31))

        assert result is None


# ---------------------------------------------------------------------------
# get_macro_context tool tests
# ---------------------------------------------------------------------------


class TestGetMacroContext:
    """Tests for the get_macro_context tool function."""

    def test_raises_when_as_of_date_is_none(self) -> None:
        """get_macro_context raises ValueError when as_of_date is None."""
        with pytest.raises(ValueError, match="as_of_date"):
            get_macro_context(as_of_date=None)

    @patch("ai_hedge_fund.data.tools.macro_tools.FredClient")
    def test_returns_macro_context_result(self, mock_client_cls: MagicMock) -> None:
        """get_macro_context returns dict with indicators, cpi_yoy_pct, gdp_growth_pct, summary_text."""
        mock_instance = MagicMock()
        mock_instance.get_latest_values.return_value = {
            "fed_funds_rate": 5.33,
            "cpi": 310.2,
            "gdp": 22801.0,
            "real_gdp": 20640.0,
            "yield_curve_spread": -0.35,
            "treasury_10y": 4.12,
            "treasury_2y": 4.47,
        }
        mock_instance.compute_cpi_yoy.return_value = 3.23
        mock_instance.compute_gdp_growth.return_value = 2.36
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, fred_api_key="test-key")
        result = get_macro_context(as_of_date=date(2024, 1, 15), settings=settings)

        assert "indicators" in result
        assert "cpi_yoy_pct" in result
        assert "gdp_growth_pct" in result
        assert "summary_text" in result
        assert isinstance(result["summary_text"], str)

    @patch("ai_hedge_fund.data.tools.macro_tools.FredClient")
    def test_summary_contains_macro_keywords(self, mock_client_cls: MagicMock) -> None:
        """Summary text mentions key macro indicators."""
        mock_instance = MagicMock()
        mock_instance.get_latest_values.return_value = {
            "fed_funds_rate": 5.33,
            "cpi": 310.2,
            "gdp": 22801.0,
            "real_gdp": 20640.0,
            "yield_curve_spread": -0.35,
            "treasury_10y": 4.12,
            "treasury_2y": 4.47,
        }
        mock_instance.compute_cpi_yoy.return_value = 3.23
        mock_instance.compute_gdp_growth.return_value = 2.36
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, fred_api_key="test-key")
        result = get_macro_context(as_of_date=date(2024, 1, 15), settings=settings)

        summary = result["summary_text"]
        assert "Federal funds" in summary or "funds rate" in summary
        assert "CPI" in summary or "Inflation" in summary
        assert "GDP" in summary
        assert "Treasury" in summary or "yield" in summary.lower()

    @patch("ai_hedge_fund.data.tools.macro_tools.FredClient")
    def test_handles_none_cpi_and_gdp(self, mock_client_cls: MagicMock) -> None:
        """get_macro_context handles None CPI YoY and GDP growth gracefully."""
        mock_instance = MagicMock()
        mock_instance.get_latest_values.return_value = {
            "fed_funds_rate": 5.33,
            "cpi": None,
            "gdp": None,
            "real_gdp": None,
            "yield_curve_spread": -0.35,
            "treasury_10y": 4.12,
            "treasury_2y": 4.47,
        }
        mock_instance.compute_cpi_yoy.return_value = None
        mock_instance.compute_gdp_growth.return_value = None
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, fred_api_key="test-key")
        result = get_macro_context(as_of_date=date(2024, 1, 15), settings=settings)

        assert result["cpi_yoy_pct"] is None
        assert result["gdp_growth_pct"] is None
        # Summary should still be generated (with "N/A" or similar)
        assert isinstance(result["summary_text"], str)

    @patch("ai_hedge_fund.data.tools.macro_tools.FredClient")
    def test_results_cached_to_db(
        self, mock_client_cls: MagicMock, db_session: Session
    ) -> None:
        """Observations are cached to MacroIndicator model when db_session provided."""
        mock_instance = MagicMock()
        mock_instance.get_latest_values.return_value = {
            "fed_funds_rate": 5.33,
            "cpi": 310.2,
            "gdp": 22801.0,
            "real_gdp": 20640.0,
            "yield_curve_spread": -0.35,
            "treasury_10y": 4.12,
            "treasury_2y": 4.47,
        }
        mock_instance.compute_cpi_yoy.return_value = 3.23
        mock_instance.compute_gdp_growth.return_value = 2.36
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, fred_api_key="test-key")
        get_macro_context(
            as_of_date=date(2024, 1, 15),
            db_session=db_session,
            settings=settings,
        )

        indicators = db_session.query(MacroIndicator).all()
        # Should cache all non-None indicators
        assert len(indicators) >= 5  # At least the non-None ones

    def test_raises_when_api_key_not_configured(self) -> None:
        """Raises ValueError when fred_api_key is empty."""
        settings = AppSettings(_env_file=None, fred_api_key="")
        with pytest.raises(ValueError, match="fred_api_key"):
            get_macro_context(as_of_date=date(2024, 1, 15), settings=settings)
