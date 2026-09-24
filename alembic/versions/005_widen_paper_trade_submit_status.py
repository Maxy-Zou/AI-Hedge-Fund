"""Widen paper_trades.submit_status for refusal audit rows.

Revision ID: 005
Revises: 004
Create Date: 2026-09-24

Phase 10 (D4) records every non-submission as its own row so an auditor can
tell "never attempted" from "attempted and refused, here is why". Phase 9
admitted submitted | rejected | refused_veto; this adds refused_review
(reviewer REJECTED) and refused_policy (neutral direction, long-only block,
no price, or sub-minimum size). The 'broker_order_id iff submitted' CHECK is
unchanged and still holds for every refusal.

The two new statuses are 14 characters, so the column widens from VARCHAR(12)
to VARCHAR(20) too. (A CHECK that admits a value the column cannot store only
fails on PostgreSQL -- SQLite ignores VARCHAR length.)

SQLite cannot ALTER ... DROP CONSTRAINT, so the change runs inside
batch_alter_table, which recreates the table with the new CHECK. downgrade
refuses to run if any row already uses a new status (would violate the
narrower CHECK and silently lose audit rows -- 09-PREMORTEM #14 analogue).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

_NEW = (
    "submit_status IN ('submitted', 'rejected', 'refused_veto', 'refused_review', 'refused_policy')"
)
_OLD = "submit_status IN ('submitted', 'rejected', 'refused_veto')"
_NAME = "ck_paper_trades_submit_status"
_OLD_WIDTH = 12
_NEW_WIDTH = 20


def upgrade() -> None:
    with op.batch_alter_table("paper_trades") as batch:
        batch.alter_column(
            "submit_status",
            existing_type=sa.String(_OLD_WIDTH),
            type_=sa.String(_NEW_WIDTH),
            existing_nullable=False,
        )
        batch.drop_constraint(_NAME, type_="check")
        batch.create_check_constraint(_NAME, _NEW)


def downgrade() -> None:
    bind = op.get_bind()
    stragglers = bind.execute(
        sa.text(
            "SELECT count(*) FROM paper_trades "
            "WHERE submit_status IN ('refused_review', 'refused_policy')"
        )
    ).scalar_one()
    if stragglers:
        raise RuntimeError(
            f"cannot downgrade: {stragglers} paper_trades row(s) use refused_review/"
            "refused_policy, which the narrower CHECK forbids -- would lose audit rows"
        )
    # Safe to narrow: the guard above proves no 14-char status remains.
    with op.batch_alter_table("paper_trades") as batch:
        batch.drop_constraint(_NAME, type_="check")
        batch.create_check_constraint(_NAME, _OLD)
        batch.alter_column(
            "submit_status",
            existing_type=sa.String(_NEW_WIDTH),
            type_=sa.String(_OLD_WIDTH),
            existing_nullable=False,
        )
