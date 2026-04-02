"""Add is_active and deactivation_reason columns to companies table.

Per D-10: soft remove via is_active=False with reason.

Revision ID: 002_add_active
Revises: 001_initial
Create Date: 2026-03-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_add_active"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_active (Boolean, default True) and deactivation_reason (String) to companies."""
    op.add_column(
        "companies",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "deactivation_reason",
            sa.String(255),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove deactivation_reason and is_active from companies."""
    op.drop_column("companies", "deactivation_reason")
    op.drop_column("companies", "is_active")
