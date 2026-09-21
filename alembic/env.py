"""Alembic environment configuration.

Loads database URL from AppSettings (which reads .env and environment
variables). Imports all models so autogenerate can detect schema changes.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import ai_hedge_fund.db.models  # noqa: F401

# Import Base and all models for autogenerate support
from ai_hedge_fund.db.base import Base
from alembic import context

# Alembic Config object
config = context.config

# Set up Python logging from config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata


def _get_database_url() -> str:
    """Load database URL from environment or AppSettings.

    Priority: DATABASE_URL env var > AppSettings default.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        from ai_hedge_fund.config import get_settings

        return get_settings().database_url
    except Exception:
        return "postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL, without creating an Engine.
    Useful for generating SQL scripts without a live database.
    """
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
