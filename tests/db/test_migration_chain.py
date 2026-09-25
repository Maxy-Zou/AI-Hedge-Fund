"""Full alembic chain (001 -> head): round trips and ORM/schema parity.

Closes two TECH-DEBT entries: migrations 001-003 were never executed by the
suite, and 001/002 created ``observed_date`` (and ``daily_prices.source``) as
nullable while the ORM declares them NOT NULL. The rest of the suite builds
tables with ``Base.metadata.create_all``, so that drift stayed invisible.

Unlike ``tests/paper/test_migration_roundtrip.py`` (which filters to structural
diffs on the paper tables), parity here is the *unfiltered* ``compare_metadata``
over every table -- nullability included. SQLite tests run by default; the
PostgreSQL copies need ``TEST_DATABASE_URL`` naming a ``*test*`` database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from ai_hedge_fund.db.base import Base
from alembic import command
from tests.paper.test_migration_roundtrip import HEAD, _alembic_config, _pg_url_or_skip, _version

V1_TABLES = (
    "sec_filings",
    "xbrl_facts",
    "daily_prices",
    "insider_trades",
    "news_articles",
    "macro_indicators",
    "portfolio_positions",
    "episodic_memory",
)
ALEMBIC_VERSION = "alembic_version"


def _restore_env(previous: str | None) -> None:
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous


@pytest.fixture()
def sqlite_cfg(tmp_path: Path) -> Iterator[tuple[Config, str]]:
    """A fresh, empty file SQLite database per test (the chain starts from base)."""
    url = f"sqlite:///{tmp_path / 'chain.sqlite'}"
    previous = os.environ.get("DATABASE_URL")
    try:
        yield _alembic_config(url), url
    finally:
        _restore_env(previous)


@pytest.fixture()
def pg_cfg() -> Iterator[tuple[Config, str]]:
    url = _pg_url_or_skip()
    previous = os.environ.get("DATABASE_URL")
    try:
        yield _alembic_config(url), url
    finally:
        _restore_env(previous)


def _revisions(cfg: Config) -> list[str]:
    """Revisions from base to head, in upgrade order."""
    return [s.revision for s in reversed(list(ScriptDirectory.from_config(cfg).walk_revisions()))]


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names()) - {ALEMBIC_VERSION}
    finally:
        engine.dispose()


def _describe(diff: tuple | list) -> str:
    """One readable line per diff; modify_* groups arrive as a list of tuples."""
    if isinstance(diff, list):
        return "; ".join(f"{d[0]} {d[2]}.{d[3]} {d[-2]!r}->{d[-1]!r}" for d in diff)
    return f"{diff[0]} {diff[1:]}"


def _schema_diffs(url: str) -> list[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()
    return [_describe(d) for d in diffs]


def _assert_round_trip(cfg: Config, url: str) -> None:
    command.upgrade(cfg, "head")
    assert _version(url) == HEAD
    assert _tables(url) == set(Base.metadata.tables), "head schema != ORM table set"
    command.downgrade(cfg, "base")
    assert _tables(url) == set(), f"downgrade to base left tables: {_tables(url)}"
    command.upgrade(cfg, "head")
    assert _version(url) == HEAD
    assert _tables(url) == set(Base.metadata.tables)


# --------------------------------------------------------------------------- chain shape


def test_chain_is_linear_from_001_to_head(sqlite_cfg: tuple[Config, str]) -> None:
    cfg, _ = sqlite_cfg
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [HEAD], "branched history or stale HEAD constant"
    revs = _revisions(cfg)
    assert revs[0] == "001"
    assert revs == [f"{n:03d}" for n in range(1, len(revs) + 1)], f"gap in chain: {revs}"


# --------------------------------------------------------------------------- SQLite


def test_sqlite_full_chain_round_trip(sqlite_cfg: tuple[Config, str]) -> None:
    """upgrade head -> downgrade base (empty) -> upgrade head, from a fresh database."""
    _assert_round_trip(*sqlite_cfg)


def test_sqlite_stepwise_down_then_up(sqlite_cfg: tuple[Config, str]) -> None:
    """Every migration's downgrade and upgrade runs on its own, one revision at a time."""
    cfg, url = sqlite_cfg
    revs = _revisions(cfg)
    command.upgrade(cfg, "head")
    for expected in reversed(revs[:-1]):
        command.downgrade(cfg, "-1")
        assert _version(url) == expected
    command.downgrade(cfg, "-1")
    assert _tables(url) == set()
    for expected in revs:
        command.upgrade(cfg, "+1")
        assert _version(url) == expected


def test_sqlite_head_matches_orm_exactly(sqlite_cfg: tuple[Config, str]) -> None:
    """Unfiltered compare_metadata: tables, columns, indexes, FKs and nullability."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    diffs = _schema_diffs(url)
    assert diffs == [], "ORM/migration drift:\n" + "\n".join(diffs)


@pytest.mark.parametrize("table", V1_TABLES)
def test_sqlite_v1_nullability_matches_orm(sqlite_cfg: tuple[Config, str], table: str) -> None:
    """Per-table view of the drift the 002 TECH-DEBT entry describes."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        reflected = {c["name"]: c["nullable"] for c in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()
    declared = {c.name: c.nullable for c in Base.metadata.tables[table].columns}
    drift = {n: (reflected.get(n), v) for n, v in declared.items() if reflected.get(n) != v}
    assert not drift, f"{table} (migration, model) nullable drift: {drift}"


# --------------------------------------------------------------------------- 008 specifics


def _insert_null_observed_position(url: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO portfolio_positions (ticker, sector, quantity, cost_basis_cents,"
                    " current_value_cents, as_of_date, observed_date)"
                    " VALUES ('NUL', 'T', 1, 100, 100, '2026-04-18 00:00:00', NULL)"
                )
            )
    finally:
        engine.dispose()


def test_008_refuses_to_upgrade_over_null_observed_date(sqlite_cfg: tuple[Config, str]) -> None:
    """No backfill: a NULL observed_date is unknowable, so the upgrade must stop."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "007")
    _insert_null_observed_position(url)
    with pytest.raises(RuntimeError, match="cannot upgrade.*portfolio_positions"):
        command.upgrade(cfg, "008")
    assert _version(url) == "007"


def test_008_downgrade_restores_nullable_observed_date(sqlite_cfg: tuple[Config, str]) -> None:
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "008")
    command.downgrade(cfg, "007")
    _insert_null_observed_position(url)  # accepted again at 007
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM portfolio_positions"))
    finally:
        engine.dispose()
    command.upgrade(cfg, "head")
    assert _version(url) == HEAD


# --------------------------------------------------------------------------- PostgreSQL


@pytest.mark.slow
def test_pg_full_chain_round_trip(pg_cfg: tuple[Config, str]) -> None:
    """Refuses (by design) if the test DB holds rows a downgrade guard protects."""
    _assert_round_trip(*pg_cfg)


@pytest.mark.slow
def test_pg_head_matches_orm_exactly(pg_cfg: tuple[Config, str]) -> None:
    cfg, url = pg_cfg
    command.upgrade(cfg, "head")
    diffs = _schema_diffs(url)
    assert diffs == [], "ORM/migration drift on PostgreSQL:\n" + "\n".join(diffs)
