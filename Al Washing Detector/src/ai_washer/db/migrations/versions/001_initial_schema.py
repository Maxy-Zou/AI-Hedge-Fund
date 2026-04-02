"""Initial schema: companies, daily_scores (monthly partitioned per D-06),
signal_details, pipeline_runs.

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Monthly partition definitions per D-06.
# Creates 12 months for 2026 + 6 months into 2027 for buffer.
MONTHLY_PARTITIONS = [
    ("daily_scores_2026_01", "2026-01-01", "2026-02-01"),
    ("daily_scores_2026_02", "2026-02-01", "2026-03-01"),
    ("daily_scores_2026_03", "2026-03-01", "2026-04-01"),
    ("daily_scores_2026_04", "2026-04-01", "2026-05-01"),
    ("daily_scores_2026_05", "2026-05-01", "2026-06-01"),
    ("daily_scores_2026_06", "2026-06-01", "2026-07-01"),
    ("daily_scores_2026_07", "2026-07-01", "2026-08-01"),
    ("daily_scores_2026_08", "2026-08-01", "2026-09-01"),
    ("daily_scores_2026_09", "2026-09-01", "2026-10-01"),
    ("daily_scores_2026_10", "2026-10-01", "2026-11-01"),
    ("daily_scores_2026_11", "2026-11-01", "2026-12-01"),
    ("daily_scores_2026_12", "2026-12-01", "2027-01-01"),
    ("daily_scores_2027_01", "2027-01-01", "2027-02-01"),
    ("daily_scores_2027_02", "2027-02-01", "2027-03-01"),
    ("daily_scores_2027_03", "2027-03-01", "2027-04-01"),
    ("daily_scores_2027_04", "2027-04-01", "2027-05-01"),
    ("daily_scores_2027_05", "2027-05-01", "2027-06-01"),
    ("daily_scores_2027_06", "2027-06-01", "2027-07-01"),
]


def upgrade() -> None:
    """Create all tables: companies, daily_scores (partitioned), signal_details, pipeline_runs."""
    # --- companies table ---
    op.create_table(
        "companies",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("ticker", sa.String(10), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("cik", sa.String(10), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("market_cap_cents", sa.BigInteger(), nullable=True),
        sa.Column(
            "aliases",
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
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- daily_scores table (monthly partitioned per D-06) ---
    # CRITICAL: Must use raw SQL for partitioned table creation.
    # Alembic's op.create_table does not support PARTITION BY.
    # Per research: composite PK (id, scored_at) required by PostgreSQL.
    op.execute(
        sa.text("""
        CREATE TABLE daily_scores (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            scored_at TIMESTAMPTZ NOT NULL,
            company_id UUID NOT NULL REFERENCES companies(id),
            composite_score SMALLINT NOT NULL,
            signal_breakdown JSONB NOT NULL,
            confidence DOUBLE PRECISION NOT NULL,
            weights_used JSONB NOT NULL,
            run_id UUID NOT NULL,
            as_of_date DATE NOT NULL,
            observed_date DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, scored_at)
        ) PARTITION BY RANGE (scored_at)
    """)
    )

    # Create monthly partitions per D-06 (monthly range partitioning)
    for name, start, end in MONTHLY_PARTITIONS:
        op.execute(
            sa.text(
                f"CREATE TABLE {name} PARTITION OF daily_scores "
                f"FOR VALUES FROM ('{start}') TO ('{end}')"
            )
        )

    # Index on daily_scores
    op.execute(
        sa.text("""
        CREATE INDEX ix_daily_scores_company_scored
        ON daily_scores (company_id, scored_at)
    """)
    )

    # --- signal_details table ---
    op.create_table(
        "signal_details",
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
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column(
            "evidence",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
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
    op.create_index(
        "ix_signal_details_company_signal_date",
        "signal_details",
        ["company_id", "signal_type", "as_of_date"],
    )

    # --- pipeline_runs table ---
    op.create_table(
        "pipeline_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column(
            "companies_processed",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "errors",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("pipeline_runs")
    op.drop_index(
        "ix_signal_details_company_signal_date", table_name="signal_details"
    )
    op.drop_table("signal_details")
    # Drop monthly partitions before parent table
    for name, _, _ in reversed(MONTHLY_PARTITIONS):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))
    op.execute(sa.text("DROP TABLE IF EXISTS daily_scores"))
    op.drop_table("companies")
