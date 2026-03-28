"""SQLAlchemy ORM models for fund-backtest.

Two tables:
- universe_tickers: Mutable registry of tracked mid-cap tickers with GICS sector.
- universe_snapshots: Append-only log of each universe refresh run.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, Date, DateTime, String, func
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
