"""Create paper_cash_events and paper_pnl_daily.

Revision ID: 007
Revises: 006
Create Date: 2026-09-25

Phase 11 mark-to-market (MTM-02/04; 11-SPEC s3). Both tables are append-only,
enforced as in migration 004: the ORM guard (db/append_only.py) at the session
and, on PostgreSQL, a BEFORE UPDATE OR DELETE trigger at the database.

The trigger *function* ``paper_append_only_guard`` is owned by migration 004;
this migration only attaches triggers to it, and its downgrade drops only
those triggers -- dropping the function would break paper_trades/paper_fills.
Trigger DDL is duplicated rather than imported so the migration stays a
frozen snapshot.

``paper_pnl_daily`` holds cumulative values, one row per (signal, trading
day); ``paper_cash_events`` holds broker dividend cash and corporate-action
activities (11-SPEC A1). tests/mtm/test_migration_007.py enforces parity with
the ORM models, CHECKs and column widths included.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

_JSON = postgresql.JSONB().with_variant(sa.JSON, "sqlite")
_TABLES = ("paper_cash_events", "paper_pnl_daily")
_CASH_TYPES_SQL = (
    "'DIV', 'DIVCGL', 'DIVCGS', 'DIVNRA', 'DIVROC', 'DIVTXEX', 'DIVWH', 'SPLIT', 'SPIN', 'MA', 'NC'"
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _trigger(table: str) -> str:
    return f"trg_{table}_append_only"


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("as_of_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observed_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def _create_paper_cash_events() -> None:
    op.create_table(
        "paper_cash_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("broker_activity_id", sa.String(64), nullable=False),
        sa.Column("activity_type", sa.String(8), nullable=False),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("net_amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("payload", _JSON, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("broker_activity_id", name="uq_paper_cash_events_activity"),
        sa.CheckConstraint(
            f"activity_type IN ({_CASH_TYPES_SQL})", name="ck_paper_cash_events_activity_type"
        ),
    )
    op.create_index(
        "ix_paper_cash_events_ticker_date", "paper_cash_events", ["ticker", "event_date"]
    )


def _create_paper_pnl_daily() -> None:
    op.create_table(
        "paper_pnl_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("episodic_memory.id"), nullable=False),
        sa.Column("pnl_date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("open_qty", sa.Integer(), nullable=False),
        sa.Column("open_cost_cents", sa.BigInteger(), nullable=False),
        sa.Column("mark_close_cents", sa.BigInteger(), nullable=False),
        sa.Column("price_source", sa.String(20), nullable=False),
        sa.Column("realized_pnl_cents", sa.BigInteger(), nullable=False),
        sa.Column("unrealized_pnl_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_pnl_cents", sa.BigInteger(), nullable=False),
        sa.Column("attribution", _JSON, nullable=False),
        sa.Column("mtm_policy_sha", sa.String(64), nullable=False),
        sa.Column("payload", _JSON, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("signal_id", "pnl_date", name="uq_paper_pnl_daily_signal_date"),
        sa.CheckConstraint("open_qty >= 0", name="ck_paper_pnl_daily_open_qty"),
        sa.CheckConstraint("open_cost_cents >= 0", name="ck_paper_pnl_daily_open_cost"),
        sa.CheckConstraint("mark_close_cents > 0", name="ck_paper_pnl_daily_mark"),
        sa.CheckConstraint(
            "total_pnl_cents = realized_pnl_cents + unrealized_pnl_cents",
            name="ck_paper_pnl_daily_total",
        ),
    )
    op.create_index("ix_paper_pnl_daily_date", "paper_pnl_daily", ["pnl_date"])


def upgrade() -> None:
    _create_paper_cash_events()
    _create_paper_pnl_daily()
    if _is_postgres():
        for table in _TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS {_trigger(table)} ON {table}")
            op.execute(
                f"CREATE TRIGGER {_trigger(table)} BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION paper_append_only_guard()"
            )


def downgrade() -> None:
    if _is_postgres():
        for table in _TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS {_trigger(table)} ON {table}")
    op.drop_index("ix_paper_pnl_daily_date", table_name="paper_pnl_daily")
    op.drop_table("paper_pnl_daily")
    op.drop_index("ix_paper_cash_events_ticker_date", table_name="paper_cash_events")
    op.drop_table("paper_cash_events")
