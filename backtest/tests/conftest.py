"""Shared pytest fixtures for fund-backtest tests."""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

BACKTEST_ROOT = Path(__file__).parent.parent


@pytest.fixture
def sample_tickers() -> list[str]:
    """A small, stable set of tickers for unit tests."""
    return ["MTSI", "WTS", "GRBK", "SWX", "CALX"]


@pytest.fixture
def sample_wiki_row() -> dict:
    """A single row as returned by the Wikipedia S&P 400 scraper (post-rename)."""
    return {
        "ticker": "MTSI",
        "name": "MACOM Technology Solutions",
        "gics_sector": "Information Technology",
        "gics_sub_industry": "Semiconductors",
    }


# ---------------------------------------------------------------------------
# Integration test fixtures — require Docker (testcontainers)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_container():
    """Start a PostgreSQL testcontainer for the full test session."""
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture(scope="session")
def db_engine(pg_container):
    """Create SQLAlchemy engine connected to the test container.

    Runs Alembic migrations once at session scope so each test shares
    the same schema without re-running migrations per test.
    """
    # testcontainers returns "postgresql+psycopg2://..." by default.
    # We use psycopg (v3) — replace the dialect prefix.
    raw_url = pg_container.get_connection_url()
    connection_url = raw_url.replace("postgresql+psycopg2", "postgresql+psycopg", 1)
    engine = create_engine(connection_url, pool_pre_ping=True)

    # Run Alembic migrations to create tables
    alembic_cfg = AlembicConfig(str(BACKTEST_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", connection_url)
    alembic_cfg.set_main_option(
        "script_location",
        str(BACKTEST_ROOT / "src/fund_backtest/db/migrations"),
    )
    alembic_command.upgrade(alembic_cfg, "head")

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Provide a clean session per test, rolling back after each test.

    Uses rollback-based isolation so tests don't affect each other
    even when sharing the session-scoped engine.
    """
    Session = sessionmaker(bind=db_engine, expire_on_commit=False)
    with Session() as session:
        yield session
        session.rollback()
