"""Add patents table for USPTO patent collection.

Revision ID: 004_add_patents
Revises: 003_add_filings
Create Date: 2026-03-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "004_add_patents"
down_revision: Union[str, None] = "003_add_filings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create patents table with indexes."""
    op.create_table(
        "patents",
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
        sa.Column("patent_id", sa.String(20), nullable=False),
        sa.Column("patent_title", sa.String(500), nullable=False),
        sa.Column("patent_date", sa.Date(), nullable=False),
        sa.Column("assignee_organization", sa.String(500), nullable=False),
        sa.Column(
            "cpc_codes",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'"),
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

    # Indexes for patents
    op.create_index(
        "ix_patents_company_date",
        "patents",
        ["company_id", "patent_date"],
    )
    op.create_index(
        "uq_patents_company_patent_id",
        "patents",
        ["company_id", "patent_id"],
        unique=True,
    )


def downgrade() -> None:
    """Drop patents table."""
    op.drop_index("uq_patents_company_patent_id", table_name="patents")
    op.drop_index("ix_patents_company_date", table_name="patents")
    op.drop_table("patents")
