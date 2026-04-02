"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2026-04-02

Creates all 4 initial tables:
  - markets: mutable entity table for Kalshi market metadata
  - market_snapshots: append-only time-series (one row per poll tick per market)
  - signals: append-only anomaly signals detected by the system
  - trades: append-only trade records (paper or live)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all 4 initial tables."""
    # markets — mutable entity table (NOT append-only)
    op.create_table(
        "markets",
        sa.Column("ticker", sa.String(50), primary_key=True, nullable=False),
        sa.Column("series_ticker", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_markets_series_ticker", "markets", ["series_ticker"])

    # market_snapshots — append-only time-series
    op.create_table(
        "market_snapshots",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ticker", sa.String(50), nullable=False),
        sa.Column("series_ticker", sa.String(50), nullable=False),
        sa.Column("yes_bid", sa.SmallInteger, nullable=False),
        sa.Column("yes_ask", sa.SmallInteger, nullable=False),
        sa.Column("no_bid", sa.SmallInteger, nullable=False),
        sa.Column("no_ask", sa.SmallInteger, nullable=False),
        sa.Column("last_price", sa.SmallInteger, nullable=False),
        sa.Column("volume", sa.Integer, nullable=False),
        sa.Column("volume_24h", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_snapshot", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_market_snapshots_ticker_captured",
        "market_snapshots",
        ["ticker", "captured_at"],
    )

    # signals — append-only anomaly signals
    op.create_table(
        "signals",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ticker", sa.String(50), nullable=False),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_signals_ticker_detected", "signals", ["ticker", "detected_at"])

    # trades — append-only trade records
    op.create_table(
        "trades",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ticker", sa.String(50), nullable=False),
        sa.Column("signal_id", UUID(as_uuid=True), nullable=True),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("contracts", sa.Integer, nullable=False),
        sa.Column("price_cents", sa.SmallInteger, nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kalshi_order_id", sa.String(100), nullable=True),
    )
    op.create_index("ix_trades_ticker_placed", "trades", ["ticker", "placed_at"])


def downgrade() -> None:
    """Drop all 4 tables in reverse dependency order."""
    op.drop_index("ix_trades_ticker_placed", table_name="trades")
    op.drop_table("trades")

    op.drop_index("ix_signals_ticker_detected", table_name="signals")
    op.drop_table("signals")

    op.drop_index(
        "ix_market_snapshots_ticker_captured", table_name="market_snapshots"
    )
    op.drop_table("market_snapshots")

    op.drop_index("ix_markets_series_ticker", table_name="markets")
    op.drop_table("markets")
