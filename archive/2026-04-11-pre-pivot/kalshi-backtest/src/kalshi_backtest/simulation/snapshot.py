"""MarketSnapshot — look-ahead firewall model for the bar-by-bar simulation engine.

Role: A passive, immutable view of a single Kalshi market at a specific point in time.
      MarketSnapshot does NOT enforce the result=None rule itself — that is BarIterator's
      responsibility. BarIterator passes suppress_result=True for any bar where
      ts < close_time, physically preventing the strategy from seeing the outcome.

Usage:
    snapshot = build_snapshot(market_row, candle_row, suppress_result=True)
    signals = strategy.generate_signals(snapshot, open_positions)

Design: _to_naive_utc is intentionally duplicated from ingestion/types.py to avoid
        coupling the simulation layer to the ingestion layer's internals.
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, field_validator


def _to_naive_utc(dt: datetime) -> datetime:
    """Strip timezone info from a datetime, treating it as UTC.

    Duplicated from ingestion/types.py intentionally — avoids coupling the
    simulation layer to the ingestion layer.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


class MarketSnapshot(BaseModel):
    """Immutable view of a Kalshi market at a single bar timestamp.

    This model is the primary interface between the BarIterator and Strategy plugins.
    All fields are validated and normalized at construction time.

    Attributes:
        ticker: Kalshi market ticker (e.g., 'KXBTC-24DEC-T50000').
        event_ticker: Parent event ticker.
        series_ticker: Series ticker.
        ts: Bar timestamp (naive UTC). Represents the start of this candlestick bar.
        close_price: Yes price at bar close in cents [0, 100]. Always present.
        open_price: Yes price at bar open in cents [0, 100]. Optional.
        high_price: Highest yes price during bar in cents [0, 100]. Optional.
        low_price: Lowest yes price during bar in cents [0, 100]. Optional.
        volume: Number of contracts traded during bar. Optional.
        close_time: Market settlement time (naive UTC).
        result: Settlement outcome — 'yes' or 'no'. None until BarIterator exposes it.
        subtitle: Human-readable market subtitle. Optional.
    """

    model_config = {"frozen": True}

    ticker: str
    event_ticker: str
    series_ticker: str
    ts: datetime
    close_price: int
    open_price: int | None = None
    high_price: int | None = None
    low_price: int | None = None
    volume: int | None = None
    close_time: datetime
    result: str | None = None
    subtitle: str | None = None

    @field_validator("ts", "close_time", mode="before")
    @classmethod
    def normalize_datetime(cls, v: datetime) -> datetime:
        """Normalize datetime fields to naive UTC."""
        return _to_naive_utc(v)

    @field_validator("close_price", mode="before")
    @classmethod
    def validate_close_price(cls, v: int) -> int:
        """close_price must be in [0, 100] cents."""
        if not 0 <= v <= 100:
            raise ValueError(f"close_price {v} out of valid range [0, 100]")
        return v

    @field_validator("open_price", "high_price", "low_price", mode="before")
    @classmethod
    def validate_optional_price(cls, v: int | None) -> int | None:
        """Optional price fields must be in [0, 100] cents when provided."""
        if v is None:
            return None
        if not 0 <= v <= 100:
            raise ValueError(f"Price {v} out of valid range [0, 100]")
        return v


def build_snapshot(
    market: dict,
    candle: dict,
    *,
    suppress_result: bool = False,
) -> MarketSnapshot:
    """Construct a MarketSnapshot from market and candle dicts.

    This is the primary factory used by BarIterator. The suppress_result flag
    is the look-ahead firewall: when True, result is set to None regardless of
    the database value. BarIterator passes suppress_result=True for all bars
    where ts < close_time.

    Args:
        market: Dict with market metadata fields (ticker, event_ticker, series_ticker,
                close_time, result, and optionally subtitle).
        candle: Dict with candlestick fields (ts, close_price, and optionally
                open_price, high_price, low_price, volume).
        suppress_result: When True, forces result=None regardless of DB value.

    Returns:
        Frozen MarketSnapshot ready for strategy consumption.
    """
    result = None if suppress_result else market.get("result")

    return MarketSnapshot(
        ticker=market["ticker"],
        event_ticker=market["event_ticker"],
        series_ticker=market["series_ticker"],
        subtitle=market.get("subtitle"),
        ts=candle["ts"],
        close_price=candle["close_price"],
        open_price=candle.get("open_price"),
        high_price=candle.get("high_price"),
        low_price=candle.get("low_price"),
        volume=candle.get("volume"),
        close_time=market["close_time"],
        result=result,
    )
