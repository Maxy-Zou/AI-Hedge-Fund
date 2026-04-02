"""Add github_repos table for GitHub repository collection.

Revision ID: 005_add_github_repos
Revises: 004_add_patents
Create Date: 2026-03-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "005_add_github_repos"
down_revision: Union[str, None] = "004_add_patents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create github_repos table with indexes."""
    op.create_table(
        "github_repos",
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
        sa.Column("repo_full_name", sa.String(255), nullable=False),
        sa.Column("repo_name", sa.String(255), nullable=False),
        sa.Column("primary_language", sa.String(50), nullable=True),
        sa.Column(
            "language_bytes",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "pushed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("is_fork", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column(
            "stargazers_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "ml_frameworks",
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

    # Indexes for github_repos
    op.create_index(
        "ix_github_repos_company_date",
        "github_repos",
        ["company_id", "observed_date"],
    )
    op.create_index(
        "uq_github_repos_company_repo_observed",
        "github_repos",
        ["company_id", "repo_full_name", "observed_date"],
        unique=True,
    )


def downgrade() -> None:
    """Drop github_repos table."""
    op.drop_index(
        "uq_github_repos_company_repo_observed", table_name="github_repos"
    )
    op.drop_index(
        "ix_github_repos_company_date", table_name="github_repos"
    )
    op.drop_table("github_repos")
