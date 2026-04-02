"""Add sec_filings and xbrl_facts tables for SEC filing collection.

Revision ID: 003_add_filings
Revises: 002_add_active
Create Date: 2026-03-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "003_add_filings"
down_revision: Union[str, None] = "002_add_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sec_filings and xbrl_facts tables with indexes."""
    # --- sec_filings table ---
    op.create_table(
        "sec_filings",
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
        sa.Column("form_type", sa.String(10), nullable=False),
        sa.Column("accession_no", sa.String(25), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("period_of_report", sa.Date(), nullable=True),
        sa.Column(
            "sections",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("content_hash", sa.String(64), nullable=True),
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

    # Indexes for sec_filings
    op.create_index(
        "ix_sec_filings_company_form_observed",
        "sec_filings",
        ["company_id", "form_type", "observed_date"],
    )
    op.create_index(
        "uq_sec_filings_company_form_accession",
        "sec_filings",
        ["company_id", "form_type", "accession_no"],
        unique=True,
    )

    # --- xbrl_facts table ---
    op.create_table(
        "xbrl_facts",
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
        sa.Column("concept", sa.String(50), nullable=False),
        sa.Column("tag", sa.String(100), nullable=False),
        sa.Column("value_cents", sa.BigInteger(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("fiscal_period", sa.String(5), nullable=False),
        sa.Column("form_type", sa.String(10), nullable=False),
        sa.Column("filed_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("accession_no", sa.String(25), nullable=False),
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

    # Indexes for xbrl_facts
    op.create_index(
        "ix_xbrl_facts_company_concept_end",
        "xbrl_facts",
        ["company_id", "concept", "end_date"],
    )
    op.create_index(
        "uq_xbrl_facts_company_concept_end_fp",
        "xbrl_facts",
        ["company_id", "concept", "end_date", "fiscal_period"],
        unique=True,
    )


def downgrade() -> None:
    """Drop xbrl_facts and sec_filings tables."""
    op.drop_index("uq_xbrl_facts_company_concept_end_fp", table_name="xbrl_facts")
    op.drop_index("ix_xbrl_facts_company_concept_end", table_name="xbrl_facts")
    op.drop_table("xbrl_facts")
    op.drop_index("uq_sec_filings_company_form_accession", table_name="sec_filings")
    op.drop_index("ix_sec_filings_company_form_observed", table_name="sec_filings")
    op.drop_table("sec_filings")
