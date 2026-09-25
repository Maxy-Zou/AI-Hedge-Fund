"""Create paper_trades and paper_fills.

Revision ID: 004
Revises: 003
Create Date: 2026-09-22

Phase 9 paper-trading ledger (PT-01..04). Both tables are append-only:
the ORM guard (db/append_only.py) refuses UPDATE/DELETE at the session,
and on PostgreSQL a BEFORE UPDATE OR DELETE trigger refuses them at the
database -- the only layer that can see raw SQL. Skipped on SQLite.

The trigger DDL is deliberately duplicated from db/append_only.py rather
than imported: a migration must be a frozen snapshot, and every statement
is idempotent (CREATE OR REPLACE / DROP ... IF EXISTS) so the same trigger
being attached by ``Base.metadata.create_all`` is harmless. The RAISE uses
``USING MESSAGE`` so the text contains no '%' for psycopg to misread.

DDL here must match the ORM models in structure;
tests/paper/test_migration_roundtrip.py enforces it (compare_metadata for
tables/columns/indexes/uniques/FKs, plus an explicit CHECK comparison).

paper_pnl_daily is deliberately NOT created here; it belongs to Phase 11
(migration 007 -- Phase 10 took 005-006), which defines its write semantics.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

_JSON = postgresql.JSONB().with_variant(sa.JSON, "sqlite")

_PG_FUNCTION = """
CREATE OR REPLACE FUNCTION paper_append_only_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'append-only table ' || TG_TABLE_NAME || ': ' || TG_OP
                  || ' not permitted; write a new row instead',
        ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql
"""


def _pg_trigger(table: str) -> tuple[str, str]:
    trg = f"trg_{table}_append_only"
    return (
        f"DROP TRIGGER IF EXISTS {trg} ON {table}",
        f"CREATE TRIGGER {trg} BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION paper_append_only_guard()",
    )


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


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


def _create_paper_trades() -> None:
    op.create_table(
        "paper_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("episodic_memory.id"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("order_type", sa.String(6), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("limit_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("submit_status", sa.String(12), nullable=False),
        sa.Column("broker_order_id", sa.String(64), nullable=True),
        sa.Column("risk_status_at_submit", sa.String(10), nullable=False),
        sa.Column("policy_sha", sa.String(64), nullable=False),
        sa.Column("review_policy_sha", sa.String(64), nullable=False),
        sa.Column("payload", _JSON, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("signal_id", "attempt_no", name="uq_paper_trades_signal_attempt"),
        sa.UniqueConstraint("broker_order_id", name="uq_paper_trades_broker_order_id"),
        sa.CheckConstraint("attempt_no >= 1", name="ck_paper_trades_attempt_no"),
        sa.CheckConstraint("quantity > 0", name="ck_paper_trades_quantity"),
        sa.CheckConstraint("side IN ('buy', 'sell')", name="ck_paper_trades_side"),
        sa.CheckConstraint("order_type IN ('market', 'limit')", name="ck_paper_trades_order_type"),
        sa.CheckConstraint(
            "submit_status IN ('submitted', 'rejected', 'refused_veto')",
            name="ck_paper_trades_submit_status",
        ),
        sa.CheckConstraint(
            "(order_type = 'limit') = (limit_price_cents IS NOT NULL)",
            name="ck_paper_trades_limit_price",
        ),
        sa.CheckConstraint(
            "(submit_status = 'submitted') = (broker_order_id IS NOT NULL)",
            name="ck_paper_trades_broker_id",
        ),
    )
    op.create_index("ix_paper_trades_signal_id", "paper_trades", ["signal_id"])
    op.create_index("ix_paper_trades_ticker_asof", "paper_trades", ["ticker", "as_of_date"])


def _create_paper_fills() -> None:
    op.create_table(
        "paper_fills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trade_id", sa.Integer(), sa.ForeignKey("paper_trades.id"), nullable=False),
        sa.Column("broker_fill_id", sa.String(64), nullable=False),
        sa.Column("filled_qty", sa.Integer(), nullable=False),
        sa.Column("fill_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _JSON, nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("broker_fill_id", name="uq_paper_fills_broker_fill_id"),
        sa.CheckConstraint("filled_qty > 0", name="ck_paper_fills_filled_qty"),
        sa.CheckConstraint("fill_price_cents > 0", name="ck_paper_fills_fill_price"),
    )
    op.create_index("ix_paper_fills_trade_id", "paper_fills", ["trade_id"])
    op.create_index("ix_paper_fills_asof", "paper_fills", ["as_of_date"])


def upgrade() -> None:
    _create_paper_trades()
    _create_paper_fills()
    if _is_postgres():
        op.execute(_PG_FUNCTION)
        for table in ("paper_trades", "paper_fills"):
            for stmt in _pg_trigger(table):
                op.execute(stmt)


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP TRIGGER IF EXISTS trg_paper_fills_append_only ON paper_fills")
        op.execute("DROP TRIGGER IF EXISTS trg_paper_trades_append_only ON paper_trades")
        op.execute("DROP FUNCTION IF EXISTS paper_append_only_guard()")
    op.drop_index("ix_paper_fills_asof", table_name="paper_fills")
    op.drop_index("ix_paper_fills_trade_id", table_name="paper_fills")
    op.drop_table("paper_fills")
    op.drop_index("ix_paper_trades_ticker_asof", table_name="paper_trades")
    op.drop_index("ix_paper_trades_signal_id", table_name="paper_trades")
    op.drop_table("paper_trades")
