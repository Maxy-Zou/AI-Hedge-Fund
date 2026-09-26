"""Make observed_date (and daily_prices.source) NOT NULL, matching the ORM.

Revision ID: 008
Revises: 007
Create Date: 2026-09-26

Migrations 001 and 002 created these columns without ``nullable=False``,
while ``TimestampMixin`` / ``DailyPrice`` declare them NOT NULL. Every test
builds tables with ``create_all``, so the drift was invisible until
tests/db/test_migration_chain.py compared the migrated schema with the models.

``observed_date`` is the collection timestamp that guards against look-ahead
bias; a row without one cannot be placed in time, and inventing a value would
fabricate provenance. So the upgrade *refuses* if any NULL exists rather than
backfilling -- resolve such rows by hand first. On a database whose columns
are already NOT NULL (built with ``create_all``) this is a no-op.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

_OBSERVED = sa.DateTime(timezone=True)
_COLUMNS: tuple[tuple[str, str, sa.types.TypeEngine], ...] = (
    ("sec_filings", "observed_date", _OBSERVED),
    ("xbrl_facts", "observed_date", _OBSERVED),
    ("daily_prices", "observed_date", _OBSERVED),
    ("daily_prices", "source", sa.String(20)),
    ("insider_trades", "observed_date", _OBSERVED),
    ("news_articles", "observed_date", _OBSERVED),
    ("macro_indicators", "observed_date", _OBSERVED),
    ("portfolio_positions", "observed_date", _OBSERVED),
)


def _null_counts() -> dict[str, int]:
    bind = op.get_bind()
    counts: dict[str, int] = {}
    for table, column, _ in _COLUMNS:
        sql = sa.text(f"SELECT count(*) FROM {table} WHERE {column} IS NULL")
        n = bind.execute(sql).scalar_one()
        if n:
            counts[f"{table}.{column}"] = n
    return counts


def _set_nullable(nullable: bool) -> None:
    tables = dict.fromkeys(t for t, _, _ in _COLUMNS)
    for table in tables:
        with op.batch_alter_table(table) as batch:
            for t, column, type_ in _COLUMNS:
                if t == table:
                    batch.alter_column(column, existing_type=type_, nullable=nullable)


def upgrade() -> None:
    nulls = _null_counts()
    if nulls:
        raise RuntimeError(
            f"cannot upgrade to 008: NULLs present {nulls}; observed_date is provenance "
            "and will not be backfilled -- resolve these rows by hand, then re-run"
        )
    _set_nullable(False)


def downgrade() -> None:
    _set_nullable(True)
