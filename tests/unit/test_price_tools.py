"""Tests for price client (yfinance + Tiingo fallback) and price retrieval tools.

Tests cover:
- PriceClient.download_yfinance: DataFrame -> cents conversion
- PriceClient.download_tiingo: API response -> cents conversion
- PriceClient.download: yfinance-first with Tiingo fallback
- PriceClient.download: PriceDownloadError when both fail
- get_price_history: as_of_date enforcement
- get_price_history: cache-first pattern via DailyPrice table
- get_price_history: temporal filtering (trade_date <= as_of_date)
- get_price_history: NL summary via format_price_summary
- get_price_history: stats computation (return, volatility, 52w range)
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings
from ai_hedge_fund.data.clients.price_client import (
    PriceClient,
    PriceDownloadError,
)
from ai_hedge_fund.data.tools.price_tools import get_price_history
from ai_hedge_fund.db.models import DailyPrice

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    """AppSettings with a Tiingo API key set."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return AppSettings(tiingo_api_key="test-tiingo-key", _env_file=None)


@pytest.fixture()
def sample_yfinance_df() -> pd.DataFrame:
    """Create a yfinance-style DataFrame with OHLCV data."""
    dates = pd.date_range("2025-01-02", periods=5, freq="B")
    data = {
        "Open": [150.00, 151.50, 149.75, 152.00, 153.25],
        "High": [152.00, 153.00, 151.00, 154.00, 155.00],
        "Low": [149.00, 150.00, 148.50, 151.00, 152.00],
        "Close": [151.00, 152.50, 150.00, 153.50, 154.50],
        "Adj Close": [150.50, 152.00, 149.50, 153.00, 154.00],
        "Volume": [1_000_000, 1_100_000, 900_000, 1_200_000, 1_050_000],
    }
    df = pd.DataFrame(data, index=dates)
    df.index.name = "Date"
    return df


@pytest.fixture()
def sample_tiingo_response() -> list[dict]:
    """Create a Tiingo-style API response."""
    return [
        {
            "date": "2025-01-02T00:00:00+00:00",
            "open": 150.00,
            "high": 152.00,
            "low": 149.00,
            "close": 151.00,
            "adjClose": 150.50,
            "volume": 1_000_000,
        },
        {
            "date": "2025-01-03T00:00:00+00:00",
            "open": 151.50,
            "high": 153.00,
            "low": 150.00,
            "close": 152.50,
            "adjClose": 152.00,
            "volume": 1_100_000,
        },
    ]


# ---------------------------------------------------------------------------
# PriceClient.download_yfinance
# ---------------------------------------------------------------------------


class TestPriceClientDownloadYfinance:
    """Tests for yfinance download and conversion."""

    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_returns_list_of_price_dicts(
        self, mock_yf: MagicMock, sample_yfinance_df: pd.DataFrame
    ) -> None:
        mock_yf.download.return_value = sample_yfinance_df
        client = PriceClient()

        result = client.download_yfinance("AAPL", date(2025, 1, 2), date(2025, 1, 8))

        assert isinstance(result, list)
        assert len(result) == 5

    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_converts_dollars_to_cents(
        self, mock_yf: MagicMock, sample_yfinance_df: pd.DataFrame
    ) -> None:
        mock_yf.download.return_value = sample_yfinance_df
        client = PriceClient()

        result = client.download_yfinance("AAPL", date(2025, 1, 2), date(2025, 1, 8))

        first = result[0]
        # $150.00 open -> 15000 cents
        assert first["open_cents"] == 15000
        # $152.00 high -> 15200 cents
        assert first["high_cents"] == 15200
        # $149.00 low -> 14900 cents
        assert first["low_cents"] == 14900
        # $151.00 close -> 15100 cents
        assert first["close_cents"] == 15100
        # $150.50 adj close -> 15050 cents
        assert first["adj_close_cents"] == 15050
        assert first["volume"] == 1_000_000

    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_price_dicts_contain_required_fields(
        self, mock_yf: MagicMock, sample_yfinance_df: pd.DataFrame
    ) -> None:
        mock_yf.download.return_value = sample_yfinance_df
        client = PriceClient()

        result = client.download_yfinance("AAPL", date(2025, 1, 2), date(2025, 1, 8))

        required_fields = {
            "trade_date",
            "open_cents",
            "high_cents",
            "low_cents",
            "close_cents",
            "adj_close_cents",
            "volume",
            "source",
        }
        for row in result:
            assert set(row.keys()) == required_fields

    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_source_is_yfinance(self, mock_yf: MagicMock, sample_yfinance_df: pd.DataFrame) -> None:
        mock_yf.download.return_value = sample_yfinance_df
        client = PriceClient()

        result = client.download_yfinance("AAPL", date(2025, 1, 2), date(2025, 1, 8))

        for row in result:
            assert row["source"] == "yfinance"

    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_trade_date_is_date_object(
        self, mock_yf: MagicMock, sample_yfinance_df: pd.DataFrame
    ) -> None:
        mock_yf.download.return_value = sample_yfinance_df
        client = PriceClient()

        result = client.download_yfinance("AAPL", date(2025, 1, 2), date(2025, 1, 8))

        for row in result:
            assert isinstance(row["trade_date"], date)


# ---------------------------------------------------------------------------
# PriceClient.download_tiingo
# ---------------------------------------------------------------------------


class TestPriceClientDownloadTiingo:
    """Tests for Tiingo download and conversion."""

    @patch("ai_hedge_fund.data.clients.price_client.TiingoClient")
    def test_returns_list_of_price_dicts(
        self, mock_tiingo_cls: MagicMock, sample_tiingo_response: list[dict]
    ) -> None:
        mock_client = MagicMock()
        mock_client.get_ticker_price.return_value = sample_tiingo_response
        mock_tiingo_cls.return_value = mock_client
        client = PriceClient(tiingo_api_key="test-key")

        result = client.download_tiingo("AAPL", date(2025, 1, 2), date(2025, 1, 3))

        assert isinstance(result, list)
        assert len(result) == 2

    @patch("ai_hedge_fund.data.clients.price_client.TiingoClient")
    def test_converts_to_cents(
        self, mock_tiingo_cls: MagicMock, sample_tiingo_response: list[dict]
    ) -> None:
        mock_client = MagicMock()
        mock_client.get_ticker_price.return_value = sample_tiingo_response
        mock_tiingo_cls.return_value = mock_client
        client = PriceClient(tiingo_api_key="test-key")

        result = client.download_tiingo("AAPL", date(2025, 1, 2), date(2025, 1, 3))

        first = result[0]
        assert first["open_cents"] == 15000
        assert first["adj_close_cents"] == 15050

    @patch("ai_hedge_fund.data.clients.price_client.TiingoClient")
    def test_source_is_tiingo(
        self, mock_tiingo_cls: MagicMock, sample_tiingo_response: list[dict]
    ) -> None:
        mock_client = MagicMock()
        mock_client.get_ticker_price.return_value = sample_tiingo_response
        mock_tiingo_cls.return_value = mock_client
        client = PriceClient(tiingo_api_key="test-key")

        result = client.download_tiingo("AAPL", date(2025, 1, 2), date(2025, 1, 3))

        for row in result:
            assert row["source"] == "tiingo"

    def test_raises_when_no_api_key(self) -> None:
        client = PriceClient(tiingo_api_key="")

        with pytest.raises(PriceDownloadError, match="Tiingo API key"):
            client.download_tiingo("AAPL", date(2025, 1, 2), date(2025, 1, 3))


# ---------------------------------------------------------------------------
# PriceClient.download (fallback logic)
# ---------------------------------------------------------------------------


class TestPriceClientDownloadFallback:
    """Tests for yfinance-first with Tiingo fallback."""

    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_uses_yfinance_first(
        self, mock_yf: MagicMock, sample_yfinance_df: pd.DataFrame
    ) -> None:
        mock_yf.download.return_value = sample_yfinance_df
        client = PriceClient(tiingo_api_key="test-key")

        result = client.download("AAPL", date(2025, 1, 2), date(2025, 1, 8))

        assert len(result) == 5
        assert result[0]["source"] == "yfinance"
        mock_yf.download.assert_called_once()

    @patch("ai_hedge_fund.data.clients.price_client.TiingoClient")
    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_falls_back_to_tiingo_on_yfinance_failure(
        self,
        mock_yf: MagicMock,
        mock_tiingo_cls: MagicMock,
        sample_tiingo_response: list[dict],
    ) -> None:
        mock_yf.download.side_effect = Exception("yfinance down")
        mock_client = MagicMock()
        mock_client.get_ticker_price.return_value = sample_tiingo_response
        mock_tiingo_cls.return_value = mock_client
        client = PriceClient(tiingo_api_key="test-key")

        result = client.download("AAPL", date(2025, 1, 2), date(2025, 1, 3))

        assert len(result) == 2
        assert result[0]["source"] == "tiingo"

    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_falls_back_to_tiingo_on_empty_yfinance_result(
        self, mock_yf: MagicMock, sample_tiingo_response: list[dict]
    ) -> None:
        mock_yf.download.return_value = pd.DataFrame()
        client = PriceClient(tiingo_api_key="test-key")

        with patch("ai_hedge_fund.data.clients.price_client.TiingoClient") as mock_tiingo_cls:
            mock_client = MagicMock()
            mock_client.get_ticker_price.return_value = sample_tiingo_response
            mock_tiingo_cls.return_value = mock_client

            result = client.download("AAPL", date(2025, 1, 2), date(2025, 1, 3))

        assert len(result) == 2

    @patch("ai_hedge_fund.data.clients.price_client.TiingoClient")
    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_raises_when_both_fail(self, mock_yf: MagicMock, mock_tiingo_cls: MagicMock) -> None:
        mock_yf.download.side_effect = Exception("yfinance down")
        mock_client = MagicMock()
        mock_client.get_ticker_price.side_effect = Exception("tiingo down")
        mock_tiingo_cls.return_value = mock_client
        client = PriceClient(tiingo_api_key="test-key")

        with pytest.raises(PriceDownloadError, match="both.*fail"):
            client.download("AAPL", date(2025, 1, 2), date(2025, 1, 8))

    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_raises_when_yfinance_fails_and_no_tiingo_key(self, mock_yf: MagicMock) -> None:
        mock_yf.download.side_effect = Exception("yfinance down")
        client = PriceClient(tiingo_api_key="")

        with pytest.raises(PriceDownloadError):
            client.download("AAPL", date(2025, 1, 2), date(2025, 1, 8))


# ---------------------------------------------------------------------------
# get_price_history: as_of_date enforcement
# ---------------------------------------------------------------------------


class TestGetPriceHistoryAsOfDate:
    """Tests for as_of_date validation via enforce_as_of_date decorator."""

    def test_raises_when_as_of_date_is_none(self) -> None:
        with pytest.raises(ValueError, match="as_of_date is required"):
            get_price_history("AAPL", as_of_date=None)


# ---------------------------------------------------------------------------
# get_price_history: cache-first pattern
# ---------------------------------------------------------------------------


class TestGetPriceHistoryCacheFirst:
    """Tests for cache read/write with DailyPrice table."""

    def test_checks_cache_first(self, db_session: Session, settings: AppSettings) -> None:
        """When sufficient cached data exists, no external API call is made."""
        as_of = date(2025, 1, 10)
        start = as_of - timedelta(days=252)

        # Seed cached data over 252 calendar days (>80% of expected trading days)
        for i in range(252):
            d = start + timedelta(days=i)
            # Skip weekends
            if d.weekday() >= 5:
                continue
            price = DailyPrice(
                ticker="AAPL",
                trade_date=d,
                open_cents=15000,
                high_cents=15200,
                low_cents=14900,
                close_cents=15100,
                adj_close_cents=15050 + i * 10,
                volume=1_000_000,
                source="yfinance",
                as_of_date=datetime(d.year, d.month, d.day, tzinfo=UTC),
            )
            db_session.add(price)
        db_session.commit()

        # The tool should NOT call any external API
        with patch("ai_hedge_fund.data.tools.price_tools.PriceClient") as mock_client_cls:
            result = get_price_history(
                "AAPL",
                as_of_date=as_of,
                lookback_days=252,
                db_session=db_session,
                settings=settings,
            )
            mock_client_cls.assert_not_called()

        assert result["ticker"] == "AAPL"
        assert isinstance(result["prices"], list)
        assert len(result["prices"]) > 0

    def test_only_returns_prices_before_as_of_date(
        self, db_session: Session, settings: AppSettings
    ) -> None:
        """Prices after as_of_date must be excluded (temporal correctness)."""
        as_of = date(2025, 1, 10)
        start = as_of - timedelta(days=252)

        # Seed enough data to hit cache threshold -- only up to as_of_date
        for i in range(260):
            d = start + timedelta(days=i)
            if d.weekday() >= 5:
                continue
            if d > as_of:
                break
            price = DailyPrice(
                ticker="AAPL",
                trade_date=d,
                open_cents=15000,
                high_cents=15200,
                low_cents=14900,
                close_cents=15100,
                adj_close_cents=15050,
                volume=1_000_000,
                source="yfinance",
                as_of_date=datetime(d.year, d.month, d.day, tzinfo=UTC),
            )
            db_session.add(price)

        # Add a future price that should NOT appear in results
        future_price = DailyPrice(
            ticker="AAPL",
            trade_date=date(2025, 1, 13),
            open_cents=16000,
            high_cents=16200,
            low_cents=15900,
            close_cents=16100,
            adj_close_cents=16050,
            volume=1_200_000,
            source="yfinance",
            as_of_date=datetime(2025, 1, 13, tzinfo=UTC),
        )
        db_session.add(future_price)
        db_session.commit()

        with patch("ai_hedge_fund.data.tools.price_tools.PriceClient") as mock_client_cls:
            result = get_price_history(
                "AAPL",
                as_of_date=as_of,
                lookback_days=252,
                db_session=db_session,
                settings=settings,
            )
            mock_client_cls.assert_not_called()

        for p in result["prices"]:
            assert p["trade_date"] <= as_of

    @patch("ai_hedge_fund.data.tools.price_tools.PriceClient")
    def test_cache_miss_calls_external_api(
        self,
        mock_client_cls: MagicMock,
        db_session: Session,
        settings: AppSettings,
    ) -> None:
        """When cache is empty, PriceClient.download is called."""
        mock_instance = MagicMock()
        mock_instance.download.return_value = [
            {
                "trade_date": date(2025, 1, 2),
                "open_cents": 15000,
                "high_cents": 15200,
                "low_cents": 14900,
                "close_cents": 15100,
                "adj_close_cents": 15050,
                "volume": 1_000_000,
                "source": "yfinance",
            },
            {
                "trade_date": date(2025, 1, 3),
                "open_cents": 15150,
                "high_cents": 15300,
                "low_cents": 15000,
                "close_cents": 15250,
                "adj_close_cents": 15200,
                "volume": 1_100_000,
                "source": "yfinance",
            },
        ]
        mock_client_cls.return_value = mock_instance

        result = get_price_history(
            "AAPL",
            as_of_date=date(2025, 1, 3),
            lookback_days=10,
            db_session=db_session,
            settings=settings,
        )

        mock_instance.download.assert_called_once()
        assert result["ticker"] == "AAPL"
        assert len(result["prices"]) == 2

    @patch("ai_hedge_fund.data.tools.price_tools.PriceClient")
    def test_cache_miss_stores_in_daily_price_table(
        self,
        mock_client_cls: MagicMock,
        db_session: Session,
        settings: AppSettings,
    ) -> None:
        """Downloaded prices are inserted into DailyPrice for future caching."""
        mock_instance = MagicMock()
        mock_instance.download.return_value = [
            {
                "trade_date": date(2025, 1, 2),
                "open_cents": 15000,
                "high_cents": 15200,
                "low_cents": 14900,
                "close_cents": 15100,
                "adj_close_cents": 15050,
                "volume": 1_000_000,
                "source": "yfinance",
            },
        ]
        mock_client_cls.return_value = mock_instance

        get_price_history(
            "AAPL",
            as_of_date=date(2025, 1, 3),
            lookback_days=10,
            db_session=db_session,
            settings=settings,
        )

        cached = db_session.query(DailyPrice).filter_by(ticker="AAPL").all()
        assert len(cached) == 1
        assert cached[0].adj_close_cents == 15050


# ---------------------------------------------------------------------------
# get_price_history: result shape and summary
# ---------------------------------------------------------------------------


class TestGetPriceHistoryResult:
    """Tests for result structure and NL summary generation."""

    @patch("ai_hedge_fund.data.tools.price_tools.PriceClient")
    def test_result_has_required_fields(
        self,
        mock_client_cls: MagicMock,
        db_session: Session,
        settings: AppSettings,
    ) -> None:
        mock_instance = MagicMock()
        mock_instance.download.return_value = [
            {
                "trade_date": date(2025, 1, 2),
                "open_cents": 15000,
                "high_cents": 15200,
                "low_cents": 14900,
                "close_cents": 15100,
                "adj_close_cents": 15050,
                "volume": 1_000_000,
                "source": "yfinance",
            },
            {
                "trade_date": date(2025, 1, 3),
                "open_cents": 15150,
                "high_cents": 15300,
                "low_cents": 15000,
                "close_cents": 15250,
                "adj_close_cents": 15200,
                "volume": 1_100_000,
                "source": "yfinance",
            },
        ]
        mock_client_cls.return_value = mock_instance

        result = get_price_history(
            "AAPL",
            as_of_date=date(2025, 1, 3),
            lookback_days=10,
            db_session=db_session,
            settings=settings,
        )

        assert "ticker" in result
        assert "prices" in result
        assert "summary_text" in result
        assert "stats" in result
        assert isinstance(result["prices"], list)
        assert isinstance(result["summary_text"], str)

    @patch("ai_hedge_fund.data.tools.price_tools.PriceClient")
    def test_summary_calls_format_price_summary(
        self,
        mock_client_cls: MagicMock,
        db_session: Session,
        settings: AppSettings,
    ) -> None:
        mock_instance = MagicMock()
        mock_instance.download.return_value = [
            {
                "trade_date": date(2025, 1, 2),
                "open_cents": 15000,
                "high_cents": 15200,
                "low_cents": 14900,
                "close_cents": 15100,
                "adj_close_cents": 15050,
                "volume": 1_000_000,
                "source": "yfinance",
            },
            {
                "trade_date": date(2025, 1, 3),
                "open_cents": 15150,
                "high_cents": 15300,
                "low_cents": 15000,
                "close_cents": 15250,
                "adj_close_cents": 15200,
                "volume": 1_100_000,
                "source": "yfinance",
            },
        ]
        mock_client_cls.return_value = mock_instance

        result = get_price_history(
            "AAPL",
            as_of_date=date(2025, 1, 3),
            lookback_days=10,
            db_session=db_session,
            settings=settings,
        )

        # Summary should mention the ticker
        assert "AAPL" in result["summary_text"]
        # Should have the as_of_date
        assert "2025-01-03" in result["summary_text"]

    @patch("ai_hedge_fund.data.tools.price_tools.PriceClient")
    def test_stats_contain_return_and_volatility(
        self,
        mock_client_cls: MagicMock,
        db_session: Session,
        settings: AppSettings,
    ) -> None:
        mock_instance = MagicMock()
        mock_instance.download.return_value = [
            {
                "trade_date": date(2025, 1, 2),
                "open_cents": 15000,
                "high_cents": 15200,
                "low_cents": 14900,
                "close_cents": 15100,
                "adj_close_cents": 15050,
                "volume": 1_000_000,
                "source": "yfinance",
            },
            {
                "trade_date": date(2025, 1, 3),
                "open_cents": 15150,
                "high_cents": 15300,
                "low_cents": 15000,
                "close_cents": 15250,
                "adj_close_cents": 15200,
                "volume": 1_100_000,
                "source": "yfinance",
            },
        ]
        mock_client_cls.return_value = mock_instance

        result = get_price_history(
            "AAPL",
            as_of_date=date(2025, 1, 3),
            lookback_days=10,
            db_session=db_session,
            settings=settings,
        )

        stats = result["stats"]
        assert "return_pct" in stats
        assert "volatility_pct" in stats
        assert "high_52w_cents" in stats
        assert "low_52w_cents" in stats

    @patch("ai_hedge_fund.data.tools.price_tools.PriceClient")
    def test_lookback_days_controls_date_range(
        self,
        mock_client_cls: MagicMock,
        settings: AppSettings,
    ) -> None:
        """get_price_history with lookback_days=252 requests ~1 year of data."""
        mock_instance = MagicMock()
        mock_instance.download.return_value = []
        mock_client_cls.return_value = mock_instance

        as_of = date(2025, 6, 15)
        get_price_history(
            "AAPL",
            as_of_date=as_of,
            lookback_days=252,
            settings=settings,
        )

        call_args = mock_instance.download.call_args
        start_date_arg = call_args[0][1]  # positional: ticker, start_date, end_date
        expected_start = as_of - timedelta(days=252)
        assert start_date_arg == expected_start


# ---------------------------------------------------------------------------
# Price value precision
# ---------------------------------------------------------------------------


class TestPriceCentsConversion:
    """Tests for dollar-to-cents conversion precision."""

    @patch("ai_hedge_fund.data.clients.price_client.yf")
    def test_all_values_are_int_cents(
        self, mock_yf: MagicMock, sample_yfinance_df: pd.DataFrame
    ) -> None:
        mock_yf.download.return_value = sample_yfinance_df
        client = PriceClient()

        result = client.download_yfinance("AAPL", date(2025, 1, 2), date(2025, 1, 8))

        for row in result:
            assert isinstance(row["open_cents"], int)
            assert isinstance(row["high_cents"], int)
            assert isinstance(row["low_cents"], int)
            assert isinstance(row["close_cents"], int)
            assert isinstance(row["adj_close_cents"], int)
            assert isinstance(row["volume"], int)
