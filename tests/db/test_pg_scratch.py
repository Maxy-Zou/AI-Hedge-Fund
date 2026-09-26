"""PostgreSQL migration tests must never change the shared test database.

The shared ``TEST_DATABASE_URL`` database is used by every branch. A migration
test that upgrades it to a branch-only head (PR #8 left it at 008) breaks the
Postgres tests on every other branch. ``tests.pg_scratch`` gives each test
module its own throwaway database; these tests pin that contract.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, make_url, text

from alembic import command
from tests.paper.test_migration_roundtrip import HEAD, _pg_url_or_skip
from tests.pg_scratch import scratch_alembic, scratch_database


def _db_exists(url: str, name: str) -> bool:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            sql = text("SELECT 1 FROM pg_database WHERE datname = :n")
            return conn.execute(sql, {"n": name}).first() is not None
    finally:
        engine.dispose()


def _revision(url: str) -> str | None:
    engine = create_engine(url)
    try:
        if "alembic_version" not in inspect(engine).get_table_names():
            return None
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def test_scratch_database_refuses_non_test_url() -> None:
    with (
        pytest.raises(ValueError, match="non-test"),
        scratch_database("postgresql+psycopg://u:p@localhost/prod"),
    ):
        pass


@pytest.mark.slow
def test_scratch_database_is_private_and_dropped() -> None:
    shared = _pg_url_or_skip()
    with scratch_database(shared) as url:
        name = make_url(url).database
        assert name != make_url(shared).database
        assert "test" in name
        assert _db_exists(shared, name)
    assert not _db_exists(shared, name), f"scratch database {name} was not dropped"


@pytest.mark.slow
def test_scratch_alembic_leaves_shared_revision_and_env_untouched() -> None:
    shared = _pg_url_or_skip()
    before_rev = _revision(shared)
    before_env = os.environ.get("DATABASE_URL")
    with scratch_alembic(shared) as (cfg, url):
        command.upgrade(cfg, "head")
        assert _revision(url) == HEAD
    assert _revision(shared) == before_rev, "migration test moved the shared test DB"
    assert os.environ.get("DATABASE_URL") == before_env
