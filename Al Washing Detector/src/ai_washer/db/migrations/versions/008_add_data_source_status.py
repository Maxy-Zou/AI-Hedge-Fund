"""Add data_source_status table for pipeline staleness tracking.

Revision ID: 008_add_data_source_status
Revises: 007_add_job_postings
Create Date: 2026-03-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "008_add_data_source_status"
down_revision: str | None = "007_add_job_postings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Pre-seeded data sources with expected cadence in hours
_DATA_SOURCES = [
    {"source_name": "sec_filings", "expected_cadence_hours": 24},
    {"source_name": "patents", "expected_cadence_hours": 168},  # 7 days
    {"source_name": "github", "expected_cadence_hours": 24},
    {"source_name": "earnings", "expected_cadence_hours": 2160},  # 90 days
    {"source_name": "job_postings", "expected_cadence_hours": 24},
    {"source_name": "xbrl_facts", "expected_cadence_hours": 24},
]


def upgrade() -> None:
    """Create data_source_status table and pre-seed with 6 data sources."""
    op.create_table(
        "data_source_status",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_name", sa.String(50), nullable=False, unique=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.String(500), nullable=True),
        sa.Column("expected_cadence_hours", sa.Integer(), nullable=False),
        sa.Column(
            "is_stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Pre-seed the 6 data sources
    data_source_status = sa.table(
        "data_source_status",
        sa.column("source_name", sa.String),
        sa.column("expected_cadence_hours", sa.Integer),
    )
    op.bulk_insert(data_source_status, _DATA_SOURCES)


def downgrade() -> None:
    """Drop data_source_status table."""
    op.drop_table("data_source_status")
