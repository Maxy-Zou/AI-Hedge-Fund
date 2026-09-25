"""Phase 9 -- migration 004 round-trip and ORM/DDL parity (PT-04, 9.1).

First alembic migration ever exercised by this test suite. Primary tests run
the real 001 -> 004 chain against a temporary *file* SQLite database (the
in-memory fixture cannot be shared with alembic's own engine). The
``compare_metadata`` test is the one that matters most: the rest of the
suite builds tables via ``Base.metadata.create_all``, so ORM/migration drift
would leave tests green and production wrong (09-PREMORTEM.md #11).

Postgres-gated tests (``@slow``) need ``TEST_DATABASE_URL`` and prove L3 --
the trigger that catches raw SQL -- plus clean downgrade of the trigger
function. They refuse any database whose name does not contain ``test``, and run in
a throwaway database on that server (``tests.pg_scratch``) so the shared one's
revision never moves.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import CheckConstraint, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ai_hedge_fund.db.base import Base
from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import EpisodicMemory, PaperFill, PaperTrade
from alembic import command
from tests.pg_scratch import scratch_alembic

REPO_ROOT = Path(__file__).resolve().parents[2]
HEAD = "008"  # latest revision; bump with every new migration
PAPER_TABLES = {"paper_trades", "paper_fills"}
V1_TABLES = {"episodic_memory", "portfolio_positions", "daily_prices", "sec_filings"}
STRUCTURAL = (
    "add_table",
    "remove_table",
    "add_column",
    "remove_column",
    "add_index",
    "remove_index",
    "add_constraint",
    "remove_constraint",
    "add_fk",
    "remove_fk",
)


def _alembic_config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    # alembic/env.py reads DATABASE_URL first; setting it here keeps the
    # production env.py untouched.
    os.environ["DATABASE_URL"] = url
    return cfg


def _diff_table(diff: tuple) -> str | None:
    kind = diff[0]
    if kind in ("add_table", "remove_table"):
        return diff[1].name
    if kind in ("add_column", "remove_column"):
        return diff[2]
    if kind in (
        "add_index",
        "remove_index",
        "add_constraint",
        "remove_constraint",
        "add_fk",
        "remove_fk",
    ):
        return diff[1].table.name
    return None


def _structural_paper_diffs(conn) -> list[tuple]:
    ctx = MigrationContext.configure(conn)
    out: list[tuple] = []
    for diff in compare_metadata(ctx, Base.metadata):
        if isinstance(diff, list):  # modify_* groups; type/nullable quirks on SQLite
            continue
        if diff[0] in STRUCTURAL and _diff_table(diff) in PAPER_TABLES:
            out.append(diff)
    return out


# --------------------------------------------------------------------------- SQLite


@pytest.fixture(scope="module")
def sqlite_cfg(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Config, str]]:
    db_path = tmp_path_factory.mktemp("alembic") / "roundtrip.sqlite"
    url = f"sqlite:///{db_path}"
    previous = os.environ.get("DATABASE_URL")
    try:
        yield _alembic_config(url), url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _version(url: str) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def test_sqlite_upgrade_head_creates_paper_tables(sqlite_cfg: tuple[Config, str]) -> None:
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    assert _version(url) == HEAD
    engine = create_engine(url)
    try:
        insp = inspect(engine)
        assert set(insp.get_table_names()) >= PAPER_TABLES
        assert {i["name"] for i in insp.get_indexes("paper_trades")} >= {
            "ix_paper_trades_signal_id",
            "ix_paper_trades_ticker_asof",
        }
        assert {i["name"] for i in insp.get_indexes("paper_fills")} >= {
            "ix_paper_fills_trade_id",
            "ix_paper_fills_asof",
        }
        assert {u["name"] for u in insp.get_unique_constraints("paper_trades")} >= {
            "uq_paper_trades_signal_attempt",
            "uq_paper_trades_broker_order_id",
        }
        assert {u["name"] for u in insp.get_unique_constraints("paper_fills")} >= {
            "uq_paper_fills_broker_fill_id"
        }
        fks = {fk["referred_table"] for fk in insp.get_foreign_keys("paper_trades")}
        assert fks == {"episodic_memory"}
        assert {fk["referred_table"] for fk in insp.get_foreign_keys("paper_fills")} == {
            "paper_trades"
        }
    finally:
        engine.dispose()


def test_sqlite_downgrade_removes_only_paper_tables_and_is_reversible(
    sqlite_cfg: tuple[Config, str],
) -> None:
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "003")
    assert _version(url) == "003"
    engine = create_engine(url)
    try:
        names = set(inspect(engine).get_table_names())
        assert not (PAPER_TABLES & names), "downgrade left paper tables behind"
        assert names >= V1_TABLES, "downgrade damaged a v1.0 table"
    finally:
        engine.dispose()
    command.upgrade(cfg, "head")  # reversible: back to head cleanly
    assert _version(url) == HEAD
    engine = create_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) >= PAPER_TABLES
    finally:
        engine.dispose()


def test_migration_matches_models(sqlite_cfg: tuple[Config, str]) -> None:
    """09-PREMORTEM #11: DDL from migration 004 == DDL from the ORM models."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            diffs = _structural_paper_diffs(conn)
    finally:
        engine.dispose()
    assert diffs == [], "ORM/migration drift on paper tables:\n" + "\n".join(map(str, diffs))


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().strip("()")).strip()


@pytest.mark.parametrize("model", [PaperTrade, PaperFill])
def test_check_constraints_match_models(sqlite_cfg: tuple[Config, str], model) -> None:
    """Review F4: compare_metadata ignores CHECKs, so compare them explicitly."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        reflected = {
            c["name"]: _norm(c["sqltext"])
            for c in inspect(engine).get_check_constraints(model.__tablename__)
        }
    finally:
        engine.dispose()
    declared = {
        c.name: _norm(str(c.sqltext))
        for c in model.__table__.constraints
        if isinstance(c, CheckConstraint)
    }
    assert set(reflected) == set(declared), f"CHECK name drift: {set(reflected) ^ set(declared)}"
    for name, text_ in declared.items():
        assert reflected[name] == text_, f"{name}: migration {reflected[name]!r} != model {text_!r}"


def test_fk_drift_is_detected_by_filter() -> None:
    """Review F4: the STRUCTURAL filter must not drop foreign-key diff kinds."""
    assert "add_fk" in STRUCTURAL and "remove_fk" in STRUCTURAL


def test_005_downgrade_narrows_then_upgrade_restores(sqlite_cfg: tuple[Config, str]) -> None:
    """005 down -> 004 CHECK (3 statuses); up -> 005 CHECK (5 statuses). Reversible."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "004")
    assert _version(url) == "004"
    command.upgrade(cfg, "head")
    assert _version(url) == HEAD


def test_006_downgrade_refuses_when_zero_quantity_rows_present(
    sqlite_cfg: tuple[Config, str],
) -> None:
    """F2: downgrading past 006 must not drop/So break refusal rows (quantity 0)."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        with Session(engine) as s:
            sig = EpisodicMemory(
                ticker="ZQ",
                sector="T",
                record_type="analysis",
                as_of_date=normalise_as_of("2026-04-18"),
                payload={"v": 1},
            )
            s.add(sig)
            s.commit()
            s.add(
                PaperTrade(
                    signal_id=sig.id,
                    ticker="ZQ",
                    side="buy",
                    order_type="market",
                    quantity=0,
                    submit_status="refused_veto",
                    broker_order_id=None,
                    risk_status_at_submit="VETOED",
                    policy_sha="a" * 64,
                    review_policy_sha="0" * 64,
                    as_of_date=normalise_as_of("2026-04-18"),
                    payload={"v": 1, "refusal_reason": "risk_vetoed"},
                )
            )
            s.commit()
    finally:
        engine.dispose()
    with pytest.raises(Exception, match="cannot downgrade"):
        command.downgrade(cfg, "005")


def test_005_downgrade_refuses_when_new_statuses_present(sqlite_cfg: tuple[Config, str]) -> None:
    """09-PREMORTEM #14 analogue: downgrade must not silently drop refusal rows."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        with Session(engine) as s:
            sig = EpisodicMemory(
                ticker="DG",
                sector="T",
                record_type="analysis",
                as_of_date=normalise_as_of("2026-04-18"),
                payload={"v": 1},
            )
            s.add(sig)
            s.commit()
            s.add(
                PaperTrade(
                    signal_id=sig.id,
                    ticker="DG",
                    side="buy",
                    order_type="market",
                    quantity=1,
                    submit_status="refused_policy",
                    broker_order_id=None,
                    risk_status_at_submit="APPROVED",
                    policy_sha="a" * 64,
                    review_policy_sha="a" * 64,
                    as_of_date=normalise_as_of("2026-04-18"),
                    payload={"v": 1, "refusal_reason": "long_only"},
                )
            )
            s.commit()
    finally:
        engine.dispose()
    with pytest.raises(Exception, match="cannot downgrade"):
        command.downgrade(cfg, "004")


def _allowed_submit_statuses() -> list[str]:
    ck = next(
        c
        for c in PaperTrade.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_paper_trades_submit_status"
    )
    return re.findall(r"'([a-z_]+)'", str(ck.sqltext))


def test_every_allowed_submit_status_fits_the_migrated_column(
    sqlite_cfg: tuple[Config, str],
) -> None:
    """Review R1: a CHECK may not admit a value the column cannot store.

    SQLite ignores VARCHAR length, so PostgreSQL alone would reject a too-long
    status -- at insert time, as a DataError nothing catches. Compare lengths
    here so the default (SQLite) suite catches it.
    """
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        cols = {c["name"]: c["type"] for c in inspect(engine).get_columns("paper_trades")}
    finally:
        engine.dispose()
    width = cols["submit_status"].length
    too_long = [s for s in _allowed_submit_statuses() if len(s) > width]
    assert not too_long, f"submit_status VARCHAR({width}) cannot hold {too_long}"


@pytest.mark.parametrize("model", [PaperTrade, PaperFill])
def test_string_column_widths_match_models(sqlite_cfg: tuple[Config, str], model) -> None:
    """Review R1: compare_metadata diffs are filtered to STRUCTURAL kinds, which
    drop modify_type -- so width drift between migration and ORM needs its own check."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        reflected = {
            c["name"]: getattr(c["type"], "length", None)
            for c in inspect(engine).get_columns(model.__tablename__)
        }
    finally:
        engine.dispose()
    declared = {c.name: c.type.length for c in model.__table__.columns if hasattr(c.type, "length")}
    drift = {n: (reflected.get(n), w) for n, w in declared.items() if reflected.get(n) != w}
    assert not drift, f"(migration, model) width drift: {drift}"


# --------------------------------------------------------------------------- PostgreSQL (L3)


def _pg_url_or_skip() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; PostgreSQL trigger tests skipped")
    if not url.startswith("postgresql"):
        pytest.skip("TEST_DATABASE_URL is not PostgreSQL")
    dbname = url.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in dbname:
        pytest.skip(f"refusing to run migrations against non-test database {dbname!r}")
    return url


@pytest.fixture(scope="module")
def pg_cfg() -> Iterator[tuple[Config, str]]:
    """A private scratch database -- never migrate the shared TEST_DATABASE_URL one."""
    with scratch_alembic(_pg_url_or_skip()) as cfg_url:
        yield cfg_url


@pytest.mark.slow
def test_pg_trigger_blocks_raw_sql(pg_cfg: tuple[Config, str]) -> None:
    """09-PREMORTEM #3: only the DB trigger can see text() SQL."""
    cfg, url = pg_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    sha = "c" * 64
    try:
        with Session(engine) as s:
            sig = EpisodicMemory(
                ticker="PGT",
                sector="Test",
                record_type="analysis",
                as_of_date=normalise_as_of("2026-04-18"),
                payload={"v": 1},
            )
            s.add(sig)
            s.commit()
            trade = PaperTrade(
                signal_id=sig.id,
                ticker="PGT",
                side="buy",
                order_type="market",
                quantity=1,
                submit_status="rejected",
                broker_order_id=None,
                risk_status_at_submit="APPROVED",
                policy_sha=sha,
                review_policy_sha=sha,
                as_of_date=normalise_as_of("2026-04-18"),
                payload={"v": 1, "t": datetime.now(UTC).isoformat()},
            )
            s.add(trade)
            s.commit()
            tid = trade.id
        with engine.begin() as conn, pytest.raises(DBAPIError) as exc:
            conn.execute(text("UPDATE paper_trades SET quantity = 2 WHERE id = :id"), {"id": tid})
        assert "append-only" in str(exc.value)
        with engine.begin() as conn, pytest.raises(DBAPIError):
            conn.execute(text("DELETE FROM paper_trades WHERE id = :id"), {"id": tid})
    finally:
        engine.dispose()


@pytest.mark.slow
def test_pg_downgrade_leaves_no_orphan_function(pg_cfg: tuple[Config, str]) -> None:
    """09-PREMORTEM #12."""
    cfg, url = pg_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "003")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            n = conn.execute(
                text("SELECT count(*) FROM pg_proc WHERE proname = 'paper_append_only_guard'")
            ).scalar()
        assert n == 0
    finally:
        engine.dispose()
    command.upgrade(cfg, "head")


@pytest.mark.slow
def test_pg_accepts_every_submit_status(pg_cfg: tuple[Config, str]) -> None:
    """Review R1: every status the CHECK admits must insert on real PostgreSQL.

    Flushed, then rolled back: the append-only trigger makes committed rows
    permanent, and leftover refusal rows (quantity 0) would block the downgrade
    tests on the next run. A too-long value still fails at flush.
    """
    cfg, url = pg_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    sha = "d" * 64
    try:
        with Session(engine) as s:
            sig = EpisodicMemory(
                ticker="PGS",
                sector="Test",
                record_type="analysis",
                as_of_date=normalise_as_of("2026-04-18"),
                payload={"v": 1},
            )
            s.add(sig)
            s.flush()
            for n, status in enumerate(_allowed_submit_statuses(), start=1):
                s.add(
                    PaperTrade(
                        signal_id=sig.id,
                        attempt_no=n,
                        ticker="PGS",
                        side="buy",
                        order_type="market",
                        quantity=1 if status in ("submitted", "rejected") else 0,
                        submit_status=status,
                        broker_order_id="pgs-order" if status == "submitted" else None,
                        risk_status_at_submit="APPROVED",
                        policy_sha=sha,
                        review_policy_sha=sha,
                        as_of_date=normalise_as_of("2026-04-18"),
                        payload={"v": 1, "status": status},
                    )
                )
                s.flush()
            s.rollback()
    finally:
        engine.dispose()
