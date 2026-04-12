"""Shared test fixtures for the AI Hedge Fund test suite."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

# Import models so they register with Base.metadata
import ai_hedge_fund.db.models  # noqa: F401
from ai_hedge_fund.config import AppSettings
from ai_hedge_fund.db.base import Base


@pytest.fixture()
def app_settings(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    """Create AppSettings with no .env file and clean environment."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return AppSettings(_env_file=None)


@pytest.fixture()
def sqlite_engine() -> Generator[Engine, None, None]:
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(sqlite_engine: Engine) -> Generator[Session, None, None]:
    """Provide a transactional database session for testing.

    Creates all tables via Base.metadata.create_all and provides
    a Session bound to the in-memory SQLite engine. Rolls back
    after each test for isolation.
    """
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
