"""SQLAlchemy ORM models for fund-backtest.

Four tables:
- universe_tickers: Mutable registry of tracked mid-cap tickers with GICS sector.
- universe_snapshots: Append-only log of each universe refresh run.
- price_bars: Append-only daily OHLCV price data in cents (immutable).
- price_anomalies: Flagged price anomalies for review.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from fund_backtest.db.base import Base, TimestampMixin


class UniverseTicker(TimestampMixin, Base):
    """Mutable registry of tracked mid-cap tickers with GICS sector.

    One row per ticker. Updated in-place on each refresh.
    is_active = False when ticker exits mid-cap range.
    Never delete rows — set is_active=False with a deactivation_reason.

    Columns:
        ticker: Exchange symbol (e.g. "AAPL"). Unique, not nullable.
        name: Company display name.
        gics_sector: GICS sector string (e.g. "Information Technology").
        gics_sub_industry: GICS sub-industry (more granular than sector).
        market_cap_cents: Latest market cap in cents (integer, not float).
        is_active: False when ticker has exited the mid-cap range.
        deactivation_reason: Why the ticker was deactivated.
        sector_source: Where GICS sector came from: "wikipedia_sp400" | "yfinance" | "manual".
        last_refreshed_at: When the ticker was last validated via yfinance.
    """

    __tablename__ = "universe_tickers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gics_sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gics_sub_industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    market_cap_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("true")
    )
    deactivation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sector_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UniverseSnapshot(Base):
    """Append-only log of each universe refresh run.

    One row per refresh. Records total count, new/removed tickers,
    and sector breakdown as JSONB for historical analysis.
    Never update or delete rows — this is an audit log.
    """

    __tablename__ = "universe_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    active_count: Mapped[int] = mapped_column(nullable=False)
    new_count: Mapped[int] = mapped_column(nullable=False)
    removed_count: Mapped[int] = mapped_column(nullable=False)
    sector_breakdown: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PriceBarORM(Base):
    """Append-only daily OHLCV price data for a single ticker.

    All prices stored in cents (integer) to avoid floating point issues.
    Never update or delete rows — this is an immutable price record.
    Use created_at to track when data was ingested (no updated_at).

    Columns:
        ticker: Exchange symbol (e.g. "AAPL"). Max 10 chars.
        bar_date: Trading date for this OHLCV bar.
        open_cents: Opening price in cents.
        high_cents: Intraday high in cents.
        low_cents: Intraday low in cents.
        close_cents: Closing price in cents.
        volume: Shares traded (not in cents).
        created_at: When this record was ingested.
    """

    __tablename__ = "price_bars"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    bar_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    high_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    low_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    close_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("ticker", "bar_date", name="uq_price_bars_ticker_date"),
    )


class PriceAnomalyORM(Base):
    """Flagged price anomalies detected during ingestion or validation.

    Records days where a ticker's price movement exceeded the configured
    anomaly threshold. is_reviewed starts False and is set True after
    manual or automated review.

    Columns:
        ticker: Exchange symbol.
        bar_date: Date of the anomalous price movement.
        anomaly_type: Classification (e.g. "return_spike_plus").
        daily_return_pct: Daily return percentage (NUMERIC for precision).
        is_reviewed: True when the anomaly has been reviewed.
        created_at: When this anomaly was flagged.
    """

    __tablename__ = "price_anomalies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    bar_date: Mapped[date] = mapped_column(Date, nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(50), nullable=False)
    daily_return_pct: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    is_reviewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "ticker", "bar_date", "anomaly_type", name="uq_price_anomalies_ticker_date_type"
        ),
    )
