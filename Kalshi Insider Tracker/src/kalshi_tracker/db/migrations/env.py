"""Alembic environment configuration for Kalshi Insider Tracker.

Reads KALSHI_TRACKER_DATABASE_URL from environment variable.
Never hardcode credentials in alembic.ini.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import models so metadata is populated
import kalshi_tracker.db.models  # noqa: F401
from kalshi_tracker.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Read database URL from environment. Never from alembic.ini."""
    url = os.environ.get("KALSHI_TRACKER_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "KALSHI_TRACKER_DATABASE_URL environment variable is required. "
            "Set it in .env or export it."
        )
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL script)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="kalshi_tracker_alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="kalshi_tracker_alembic_version",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
