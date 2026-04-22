"""Create portfolio_positions table.

Revision ID: 002
Revises: 001
Create Date: 2026-04-22

Adds the Phase 6 ``portfolio_positions`` table for risk-check portfolio
state. Append-only per CLAUDE.md financial-time-series convention: each
``(ticker, as_of_date)`` pair is unique; resizing a position writes a new
row with a new ``as_of_date`` rather than updating the existing row.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(10), nullable=False, index=True),
        sa.Column("sector", sa.String(50), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("cost_basis_cents", sa.BigInteger(), nullable=False),
        sa.Column("current_value_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "instrument_type",
            sa.String(20),
            nullable=False,
            server_default="equity",
        ),
        sa.Column("as_of_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observed_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "ticker",
            "as_of_date",
            name="uq_portfolio_positions_ticker_asof",
        ),
    )


def downgrade() -> None:
    op.drop_table("portfolio_positions")
