"""Create episodic_memory table.

Revision ID: 003
Revises: 002
Create Date: 2026-04-22

Phase 7 append-only episodic memory table (MEM-01). Stores completed
analyses and trade outcomes. Hot-path filter columns + JSONB payload.
NO UniqueConstraint: duplicates-by-design (multiple analyses per day
are allowed; contrast with portfolio_positions).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "episodic_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("sector", sa.String(50), nullable=False, server_default="Unknown"),
        sa.Column("record_type", sa.String(20), nullable=False),
        sa.Column("signal_direction", sa.String(10), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("outcome_pct", sa.Float(), nullable=True),
        sa.Column("linked_analysis_id", sa.BigInteger(), nullable=True),
        sa.Column("policy_sha", sa.String(64), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB().with_variant(sa.JSON, "sqlite"),
            nullable=False,
        ),
        sa.Column("as_of_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observed_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_episodic_ticker_asof", "episodic_memory", ["ticker", "as_of_date"])
    op.create_index("ix_episodic_sector_asof", "episodic_memory", ["sector", "as_of_date"])


def downgrade() -> None:
    op.drop_index("ix_episodic_sector_asof", table_name="episodic_memory")
    op.drop_index("ix_episodic_ticker_asof", table_name="episodic_memory")
    op.drop_table("episodic_memory")
