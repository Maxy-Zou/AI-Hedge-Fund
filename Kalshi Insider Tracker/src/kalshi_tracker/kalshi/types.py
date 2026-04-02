"""Typed domain contracts for Kalshi market data.

MarketSnapshot is the canonical representation of a market at a point in time.
It is the contract between the KalshiClient (producer) and all downstream consumers
(polling loop, signal detectors, dashboard). Immutable by design (frozen dataclass).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class MarketSnapshot:
    """Normalized view of a Kalshi market at a single point in time.

    Prices are integer cents (0-99). The Kalshi API returns Union[StrictFloat, StrictInt]
    for price fields — always normalize to int via round() before constructing.

    All timestamps are UTC-aware (timezone-aware datetime objects).
    """

    market_id: str          # same as ticker (Kalshi uses ticker as stable market ID)
    ticker: str
    series_ticker: str
    title: str
    yes_bid: int            # cents (0-99)
    yes_ask: int            # cents (0-99)
    no_bid: int             # cents (0-99)
    no_ask: int             # cents (0-99)
    last_price: int         # cents (0-99)
    volume: int             # total lifetime contracts traded
    volume_24h: int         # 24-hour volume
    status: str             # 'active' | 'closed' | 'settled'
    captured_at: datetime   # UTC timestamp when this snapshot was taken

    @classmethod
    def from_sdk_market(
        cls,
        market: object,
        captured_at: datetime | None = None,
    ) -> MarketSnapshot:
        """Convert a kalshi_python SDK Market object to a typed MarketSnapshot.

        Args:
            market: kalshi_python.models.Market instance from the SDK.
            captured_at: Snapshot timestamp. Defaults to datetime.now(UTC) if None.

        Returns:
            Immutable MarketSnapshot with all prices normalized to int.
        """
        ts = captured_at or datetime.now(UTC)
        return cls(
            market_id=market.ticker,  # type: ignore[attr-defined]
            ticker=market.ticker,  # type: ignore[attr-defined]
            series_ticker=market.series_ticker,  # type: ignore[attr-defined]
            title=getattr(market, "title", ""),
            yes_bid=int(round(market.yes_bid or 0)),  # type: ignore[attr-defined]
            yes_ask=int(round(market.yes_ask or 0)),  # type: ignore[attr-defined]
            no_bid=int(round(market.no_bid or 0)),  # type: ignore[attr-defined]
            no_ask=int(round(market.no_ask or 0)),  # type: ignore[attr-defined]
            last_price=int(round(market.last_price or 0)),  # type: ignore[attr-defined]
            volume=int(market.volume or 0),  # type: ignore[attr-defined]
            volume_24h=int(market.volume_24h or 0),  # type: ignore[attr-defined]
            status=market.status or "active",  # type: ignore[attr-defined]
            captured_at=ts,
        )
