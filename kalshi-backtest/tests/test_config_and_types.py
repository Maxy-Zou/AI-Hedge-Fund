"""Tests for KalshiBacktestSettings config and Pydantic data types.

Covers:
- Config validation (required fields, .pem extension enforcement)
- CandlestickRecord construction from Unix epoch
- CandlestickRecord price range validation
- MarketRecord timezone normalization
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError


class TestKalshiBacktestSettings:
    """Test suite for KalshiBacktestSettings."""

    def test_valid_settings_construction(self) -> None:
        """Settings construct without error given required fields."""
        from kalshi_backtest.config import KalshiBacktestSettings

        s = KalshiBacktestSettings(api_key_id="test-key", private_key_path=Path("key.pem"))
        assert s.api_key_id == "test-key"
        assert s.rate_limit_rpm == 60
        assert s.api_base_url == "https://demo-api.kalshi.co/trade-api/v2"
        assert s.db_path == Path("kalshi_backtest.duckdb")

    def test_invalid_key_extension_raises(self) -> None:
        """Settings raise ValueError when private_key_path is not .pem or .key."""
        from kalshi_backtest.config import KalshiBacktestSettings

        with pytest.raises((ValidationError, ValueError), match=".*pem.*|.*must point.*"):
            KalshiBacktestSettings(api_key_id="test", private_key_path=Path("key.txt"))

    def test_valid_key_extension(self) -> None:
        """Settings accept .pem and .key extensions."""
        from kalshi_backtest.config import KalshiBacktestSettings

        s = KalshiBacktestSettings(api_key_id="test", private_key_path=Path("key.key"))
        assert s.private_key_path.suffix == ".key"

    def test_load_settings_function_exists(self) -> None:
        """load_settings() is importable and callable."""
        from kalshi_backtest.config import load_settings  # noqa: F401


class TestCandlestickRecord:
    """Test suite for CandlestickRecord Pydantic model."""

    def test_construct_from_unix_epoch(self) -> None:
        """CandlestickRecord accepts Unix epoch int for ts field."""
        from kalshi_backtest.ingestion.types import CandlestickRecord

        record = CandlestickRecord(ticker="KXBTC-24DEC31-B50000", ts=1735689600, close_price=50)
        assert isinstance(record.ts, datetime)
        assert record.ts.tzinfo is None  # naive UTC

    def test_construct_from_datetime(self) -> None:
        """CandlestickRecord accepts a naive datetime for ts field."""
        from kalshi_backtest.ingestion.types import CandlestickRecord

        ts = datetime(2025, 1, 1, 0, 0, 0)
        record = CandlestickRecord(ticker="X", ts=ts, close_price=42)
        assert record.ts == ts
        assert record.ts.tzinfo is None

    def test_tz_aware_ts_stripped(self) -> None:
        """CandlestickRecord strips tzinfo from tz-aware ts field."""
        from kalshi_backtest.ingestion.types import CandlestickRecord

        ts_aware = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        record = CandlestickRecord(ticker="X", ts=ts_aware, close_price=42)
        assert record.ts.tzinfo is None

    def test_price_out_of_range_raises(self) -> None:
        """CandlestickRecord raises ValueError when close_price > 100."""
        from kalshi_backtest.ingestion.types import CandlestickRecord

        with pytest.raises(ValidationError, match=".*range.*|.*0-100.*"):
            CandlestickRecord(ticker="X", ts=1735689600, close_price=150)

    def test_price_zero_valid(self) -> None:
        """CandlestickRecord accepts close_price=0."""
        from kalshi_backtest.ingestion.types import CandlestickRecord

        record = CandlestickRecord(ticker="X", ts=1735689600, close_price=0)
        assert record.close_price == 0

    def test_price_hundred_valid(self) -> None:
        """CandlestickRecord accepts close_price=100."""
        from kalshi_backtest.ingestion.types import CandlestickRecord

        record = CandlestickRecord(ticker="X", ts=1735689600, close_price=100)
        assert record.close_price == 100

    def test_model_is_frozen(self) -> None:
        """CandlestickRecord is immutable (frozen=True)."""
        from kalshi_backtest.ingestion.types import CandlestickRecord

        record = CandlestickRecord(ticker="X", ts=1735689600, close_price=50)
        with pytest.raises(Exception):  # ValidationError or TypeError for frozen models
            record.close_price = 60  # type: ignore[misc]


class TestMarketRecord:
    """Test suite for MarketRecord Pydantic model."""

    def test_tz_aware_datetime_stripped(self) -> None:
        """MarketRecord strips tzinfo from all datetime fields on construction."""
        from kalshi_backtest.ingestion.types import MarketRecord

        open_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        close_time = datetime(2025, 12, 31, tzinfo=timezone.utc)
        record = MarketRecord(
            ticker="KXBTC-25",
            event_ticker="KXBTC",
            series_ticker="KXBTC",
            open_time=open_time,
            close_time=close_time,
            status="active",
        )
        assert record.open_time.tzinfo is None
        assert record.close_time.tzinfo is None

    def test_result_nullable(self) -> None:
        """MarketRecord result defaults to None for unsettled markets."""
        from kalshi_backtest.ingestion.types import MarketRecord

        record = MarketRecord(
            ticker="X",
            event_ticker="EV",
            series_ticker="S",
            open_time=datetime(2025, 1, 1),
            close_time=datetime(2025, 12, 31),
            status="active",
        )
        assert record.result is None

    def test_model_is_frozen(self) -> None:
        """MarketRecord is immutable (frozen=True)."""
        from kalshi_backtest.ingestion.types import MarketRecord

        record = MarketRecord(
            ticker="X",
            event_ticker="EV",
            series_ticker="S",
            open_time=datetime(2025, 1, 1),
            close_time=datetime(2025, 12, 31),
            status="active",
        )
        with pytest.raises(Exception):
            record.status = "closed"  # type: ignore[misc]
