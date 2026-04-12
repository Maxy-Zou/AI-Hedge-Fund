"""Pydantic models for Kalshi API responses and DuckDB storage records.

These are the immutable data contracts that flow between the API clients
and the storage layer. All datetime fields are naive UTC.

Design: frozen=True enforces immutability — fund-wide convention.
        Validators strip tzinfo on datetime fields before storage.
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, field_validator


def _to_naive_utc(dt: datetime | str | int) -> datetime:
    """Coerce to naive UTC datetime from datetime, ISO string, or Unix epoch int.

    Kalshi API returns ISO strings (historical) or tz-aware datetimes (SDK).
    DuckDB TIMESTAMP columns store naive UTC — normalize before writing.
    """
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    elif isinstance(dt, int):
        dt = datetime.fromtimestamp(dt, tz=UTC)
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


class MarketRecord(BaseModel):
    """Normalized Kalshi market metadata for DuckDB storage.

    Maps to the `markets` table. Mutable fields (status, result)
    are overwritten on re-ingestion via ON CONFLICT DO UPDATE.
    """

    model_config = {"frozen": True}

    ticker: str
    event_ticker: str
    series_ticker: str
    subtitle: str | None = None
    open_time: datetime
    close_time: datetime
    expiration_time: datetime | None = None
    status: str  # initialized|active|closed|settled|determined
    result: str | None = None  # 'yes'|'no' — None until settled

    @field_validator("open_time", "close_time", "expiration_time", mode="before")
    @classmethod
    def normalize_datetime(cls, v: datetime | str | int | None) -> datetime | None:
        """Coerce ISO string, epoch int, or datetime to naive UTC for DuckDB."""
        if v is None:
            return None
        return _to_naive_utc(v)


class CandlestickRecord(BaseModel):
    """Daily candlestick snapshot for a single Kalshi market.

    Maps to the `candles` table. Append-only — never overwritten.
    Prices are in integer cents (0-100).
    """

    model_config = {"frozen": True}

    ticker: str
    ts: datetime  # candle start time, naive UTC (daily = midnight UTC)
    open_price: int | None = None  # yes price in cents (0-100)
    high_price: int | None = None
    low_price: int | None = None
    close_price: int  # yes price in cents (0-100), required
    volume: int | None = None

    @field_validator("ts", mode="before")
    @classmethod
    def normalize_ts(cls, v: int | datetime) -> datetime:
        """Accept Unix epoch int (from Kalshi API) or datetime. Returns naive UTC datetime."""
        if isinstance(v, int):
            # Convert Unix epoch to naive UTC datetime. fromtimestamp with UTC then strip tzinfo
            # to match DuckDB TIMESTAMP (naive UTC) storage convention.
            return datetime.fromtimestamp(v, tz=UTC).replace(tzinfo=None)
        return _to_naive_utc(v)

    @field_validator("close_price", "open_price", "high_price", "low_price", mode="before")
    @classmethod
    def validate_price_range(cls, v: int | None) -> int | None:
        """Prices must be 0-100 cents. Raises if out of range."""
        if v is None:
            return None
        if not 0 <= v <= 100:
            raise ValueError(f"Price {v} out of valid range 0-100 cents")
        return v
