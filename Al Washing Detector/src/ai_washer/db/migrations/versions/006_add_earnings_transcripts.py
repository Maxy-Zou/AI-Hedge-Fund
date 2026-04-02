"""Add earnings_transcripts table for earnings call transcript collection.

Revision ID: 006_add_earnings_transcripts
Revises: 005_add_github_repos
Create Date: 2026-03-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "006_add_earnings_transcripts"
down_revision: str | None = "005_add_github_repos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create earnings_transcripts table with indexes."""
    op.create_table(
        "earnings_transcripts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_quarter", sa.SmallInteger(), nullable=False),
        sa.Column("transcript_date", sa.Date(), nullable=True),
        sa.Column(
            "transcript_text",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            server_default="earningscall",
        ),
        sa.Column(
            "collection_metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "observed_date",
            sa.Date(),
            nullable=False,
            server_default=sa.func.current_date(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes for earnings_transcripts
    op.create_index(
        "ix_earnings_transcripts_company_date",
        "earnings_transcripts",
        ["company_id", "observed_date"],
    )
    op.create_index(
        "uq_earnings_transcripts_company_year_quarter",
        "earnings_transcripts",
        ["company_id", "fiscal_year", "fiscal_quarter"],
        unique=True,
    )


def downgrade() -> None:
    """Drop earnings_transcripts table."""
    op.drop_index(
        "uq_earnings_transcripts_company_year_quarter",
        table_name="earnings_transcripts",
    )
    op.drop_index(
        "ix_earnings_transcripts_company_date",
        table_name="earnings_transcripts",
    )
    op.drop_table("earnings_transcripts")
