"""Allow quantity 0 on refusal rows; keep submitted orders positive.

Revision ID: 006
Revises: 005
Create Date: 2026-09-24

Phase 10 (D4) records every refusal as its own paper_trades row, but a refusal
has no positive quantity to record (a veto or missing price is refused before
sizing; below_min_size is zero by definition). Phase 9's ``quantity > 0`` CHECK
made such a row impossible. This relaxes it to ``quantity >= 0`` and adds a
paired CHECK so a *submitted* order is still strictly positive -- 0 shares means
nothing was sent.
"""

from __future__ import annotations

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

_QTY = "ck_paper_trades_quantity"
_SUBMITTED_QTY = "ck_paper_trades_submitted_qty"
_SUBMITTED_QTY_SQL = "submit_status <> 'submitted' OR quantity > 0"


def upgrade() -> None:
    with op.batch_alter_table("paper_trades") as batch:
        batch.drop_constraint(_QTY, type_="check")
        batch.create_check_constraint(_QTY, "quantity >= 0")
        batch.create_check_constraint(_SUBMITTED_QTY, _SUBMITTED_QTY_SQL)


def downgrade() -> None:
    with op.batch_alter_table("paper_trades") as batch:
        batch.drop_constraint(_SUBMITTED_QTY, type_="check")
        batch.drop_constraint(_QTY, type_="check")
        batch.create_check_constraint(_QTY, "quantity > 0")
