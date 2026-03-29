"""Create price_bars and price_anomalies tables.

Revision ID: 002
Revises: 001
Create Date: 2026-03-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_bars",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("bar_date", sa.Date(), nullable=False),
        sa.Column("open_cents", sa.BigInteger(), nullable=False),
        sa.Column("high_cents", sa.BigInteger(), nullable=False),
        sa.Column("low_cents", sa.BigInteger(), nullable=False),
        sa.Column("close_cents", sa.BigInteger(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "bar_date", name="uq_price_bars_ticker_date"),
    )
    op.create_index("ix_price_bars_ticker", "price_bars", ["ticker"])
    op.create_index("ix_price_bars_bar_date", "price_bars", ["bar_date"])
    op.create_index("ix_price_bars_ticker_date", "price_bars", ["ticker", "bar_date"])

    op.create_table(
        "price_anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("bar_date", sa.Date(), nullable=False),
        sa.Column("anomaly_type", sa.String(50), nullable=False),
        sa.Column("daily_return_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column(
            "is_reviewed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticker", "bar_date", "anomaly_type", name="uq_price_anomalies_ticker_date_type"
        ),
    )
    op.create_index("ix_price_anomalies_ticker", "price_anomalies", ["ticker"])
    op.create_index(
        "ix_price_anomalies_reviewed",
        "price_anomalies",
        ["is_reviewed"],
        postgresql_where=sa.text("is_reviewed = false"),
    )


def downgrade() -> None:
    op.drop_index("ix_price_anomalies_reviewed", table_name="price_anomalies")
    op.drop_index("ix_price_anomalies_ticker", table_name="price_anomalies")
    op.drop_table("price_anomalies")
    op.drop_index("ix_price_bars_ticker_date", table_name="price_bars")
    op.drop_index("ix_price_bars_bar_date", table_name="price_bars")
    op.drop_index("ix_price_bars_ticker", table_name="price_bars")
    op.drop_table("price_bars")
