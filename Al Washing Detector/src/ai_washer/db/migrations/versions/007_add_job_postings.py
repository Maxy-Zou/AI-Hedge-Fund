"""Add job_postings table for job posting lifecycle tracking.

Revision ID: 007_add_job_postings
Revises: 006_add_earnings_transcripts
Create Date: 2026-03-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "007_add_job_postings"
down_revision: str | None = "006_add_earnings_transcripts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create job_postings table with indexes."""
    op.create_table(
        "job_postings",
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
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company_name_raw", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("job_url", sa.String(1000), nullable=True),
        sa.Column("source_site", sa.String(50), nullable=False),
        sa.Column("role_classification", sa.String(20), nullable=False),
        sa.Column("dedup_hash", sa.String(64), nullable=False),
        sa.Column("first_seen", sa.Date(), nullable=False),
        sa.Column("last_seen", sa.Date(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "collection_metadata",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # Indexes for job_postings
    op.create_index(
        "ix_job_postings_company_date",
        "job_postings",
        ["company_id", "first_seen"],
    )
    op.create_index(
        "uq_job_postings_dedup_hash",
        "job_postings",
        ["dedup_hash"],
        unique=True,
    )


def downgrade() -> None:
    """Drop job_postings table."""
    op.drop_index("uq_job_postings_dedup_hash", table_name="job_postings")
    op.drop_index("ix_job_postings_company_date", table_name="job_postings")
    op.drop_table("job_postings")
