"""ORM models for Kalshi Insider Tracker.

Table layout:
  markets          — mutable entity table (ticker, metadata, status)
  market_snapshots — append-only time-series (one row per poll tick per market)
  signals          — append-only (one row per detected anomaly)
  trades           — append-only (one row per executed or simulated trade)

Prices are stored as SmallInteger (0-99 integer cents). Kalshi returns prices in cents
(45 means 45¢ / 45% probability). Never divide by 100 before storage.
All DateTime columns use timezone=True (UTC).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kalshi_tracker.db.base import AppendOnlyMixin, Base


class Market(Base):
    """Mutable entity table for Kalshi market metadata.

    NOT append-only — metadata (status, close_time) is updated on upsert.
    Signal and Trade tables reference market_ticker (string FK by design,
    avoiding FK constraint complexity on a high-append table).
    """

    __tablename__ = "markets"

    ticker: Mapped[str] = mapped_column(String(50), primary_key=True)
    series_ticker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # 'active' | 'closed' | 'settled'
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    close_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class MarketSnapshot(AppendOnlyMixin, Base):
    """Append-only market state snapshot captured on each poll tick.

    One row per (ticker, captured_at) — never updated or deleted (LOG-03).
    High-volume table: expect one row per active market per 5-10 seconds.
    """

    __tablename__ = "market_snapshots"
    __table_args__ = (
        Index("ix_market_snapshots_ticker_captured", "ticker", "captured_at"),
    )

    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    series_ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    # Prices in integer cents (0-99). Kalshi API returns cents. Never store as float.
    yes_bid: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    yes_ask: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    no_bid: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    no_ask: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    last_price: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_24h: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class Signal(AppendOnlyMixin, Base):
    """Append-only anomaly signal detected by the system.

    One row per detection event. Never updated or deleted (LOG-03).
    Populated in Phase 3 (signal detectors). Schema defined here for FK integrity.
    """

    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_ticker_detected", "ticker", "detected_at"),
    )

    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    # 'volume_spike' | 'price_move' | etc.
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)  # 0.0 – 1.0
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Trade(AppendOnlyMixin, Base):
    """Append-only trade record (paper or live).

    One row per trade placed (or simulated). Never updated or deleted (LOG-03).
    mode: 'paper' | 'live'. Populated in Phase 4 (trade executor).
    """

    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_ticker_placed", "ticker", "placed_at"),
    )

    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    # FK to signals.id (soft reference — avoids FK constraint on high-append table)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)   # 'yes' | 'no'
    contracts: Mapped[int] = mapped_column(Integer, nullable=False)
    price_cents: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # entry price in cents
    mode: Mapped[str] = mapped_column(String(10), nullable=False)   # 'paper' | 'live'
    # 'pending' | 'filled' | 'rejected'
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # None for paper trades
    kalshi_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
