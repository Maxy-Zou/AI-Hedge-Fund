"""Shared test fixtures for the AI Hedge Fund test suite."""

from __future__ import annotations

import os
from collections.abc import Generator

# Agent modules call create_agent() at import time, which requires a key, so any
# module importing the graph fails collection without one. Default it here so an
# isolated run (e.g. one file) collects like the full suite. The value must keep
# the "test-key" prefix: _has_real_api_key() in test_graph.py and
# test_research_pipeline.py treats any other value as a real key and would
# attempt live LLM calls.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

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
