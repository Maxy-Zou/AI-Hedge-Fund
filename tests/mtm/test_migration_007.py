"""Phase 11 T3 -- migration 007: paper_pnl_daily + paper_cash_events (11-SPEC s3).

Same approach as ``tests/paper/test_migration_roundtrip.py`` (whose helpers are
reused): the real alembic chain against a file SQLite DB, ORM/DDL parity incl.
CHECKs and widths, and PostgreSQL-gated trigger tests (``TEST_DATABASE_URL``,
database name must contain ``test``).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import CheckConstraint, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from ai_hedge_fund.db.append_only import AppendOnlyViolation, guarded_tables
from ai_hedge_fund.db.base import Base
from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import EpisodicMemory, PaperCashEvent, PaperPnlDaily
from alembic import command
from tests.paper.test_migration_roundtrip import (
    HEAD,
    STRUCTURAL,
    _alembic_config,
    _diff_table,
    _norm,
    _pg_url_or_skip,
    _version,
)

MTM_TABLES = {"paper_pnl_daily", "paper_cash_events"}
SHA = "e" * 64


@pytest.fixture(scope="module")
def sqlite_cfg(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Config, str]]:
    url = f"sqlite:///{tmp_path_factory.mktemp('alembic007') / 'mtm.sqlite'}"
    previous = os.environ.get("DATABASE_URL")
    try:
        yield _alembic_config(url), url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _signal(s: Session, ticker: str = "MTM") -> int:
    row = EpisodicMemory(
        ticker=ticker,
        sector="Test",
        record_type="analysis",
        as_of_date=normalise_as_of("2026-09-01"),
        payload={"schema_version": 2},
    )
    s.add(row)
    s.commit()
    return row.id


def _pnl(signal_id: int, **overrides: object) -> PaperPnlDaily:
    values: dict = {
        "signal_id": signal_id,
        "pnl_date": date(2026, 9, 2),
        "ticker": "MTM",
        "open_qty": 10,
        "open_cost_cents": 100_000,
        "mark_close_cents": 10_500,
        "price_source": "yfinance",
        "realized_pnl_cents": 0,
        "unrealized_pnl_cents": 5_000,
        "total_pnl_cents": 5_000,
        "attribution": {"schema": "v2"},
        "mtm_policy_sha": SHA,
        "payload": {"fill_ids": [1]},
        "as_of_date": normalise_as_of("2026-09-02"),
    }
    return PaperPnlDaily(**{**values, **overrides})


def _cash(**overrides: object) -> PaperCashEvent:
    values: dict = {
        "broker_activity_id": "20260902::abc",
        "activity_type": "DIV",
        "ticker": "MTM",
        "event_date": date(2026, 9, 2),
        "net_amount_cents": 240,
        "payload": {"id": "20260902::abc"},
        "as_of_date": normalise_as_of("2026-09-02"),
    }
    return PaperCashEvent(**{**values, **overrides})


# --------------------------------------------------------------------------- structure


def test_upgrade_head_creates_mtm_tables(sqlite_cfg: tuple[Config, str]) -> None:
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    assert _version(url) == HEAD
    engine = create_engine(url)
    try:
        insp = inspect(engine)
        assert set(insp.get_table_names()) >= MTM_TABLES
        assert {u["name"] for u in insp.get_unique_constraints("paper_pnl_daily")} == {
            "uq_paper_pnl_daily_signal_date"
        }
        assert {u["name"] for u in insp.get_unique_constraints("paper_cash_events")} == {
            "uq_paper_cash_events_activity"
        }
        assert "ix_paper_pnl_daily_date" in {i["name"] for i in insp.get_indexes("paper_pnl_daily")}
        assert "ix_paper_cash_events_ticker_date" in {
            i["name"] for i in insp.get_indexes("paper_cash_events")
        }
        fks = {fk["referred_table"] for fk in insp.get_foreign_keys("paper_pnl_daily")}
        assert fks == {"episodic_memory"}
    finally:
        engine.dispose()


def test_parity_with_orm(sqlite_cfg: tuple[Config, str]) -> None:
    """11-PREMORTEM #8: DDL from migration 007 == DDL from the ORM models."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            diffs = [
                d
                for d in compare_metadata(MigrationContext.configure(conn), Base.metadata)
                if not isinstance(d, list) and d[0] in STRUCTURAL and _diff_table(d) in MTM_TABLES
            ]
    finally:
        engine.dispose()
    assert diffs == [], "ORM/migration drift:\n" + "\n".join(map(str, diffs))


@pytest.mark.parametrize("model", [PaperPnlDaily, PaperCashEvent])
def test_check_constraints_match_models(sqlite_cfg: tuple[Config, str], model) -> None:
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
    assert declared, "model declares no CHECKs"
    assert reflected == declared


@pytest.mark.parametrize("model", [PaperPnlDaily, PaperCashEvent])
def test_string_column_widths_match_models(sqlite_cfg: tuple[Config, str], model) -> None:
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
    assert {n: reflected.get(n) for n in declared} == declared


def test_roundtrip_leaves_no_orphans(sqlite_cfg: tuple[Config, str]) -> None:
    """11-PREMORTEM #8: downgrade -1 removes only 007's tables; upgrade restores them."""
    cfg, url = sqlite_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "006")
    engine = create_engine(url)
    try:
        names = set(inspect(engine).get_table_names())
        assert not (MTM_TABLES & names)
        assert {"paper_trades", "paper_fills", "episodic_memory"} <= names
    finally:
        engine.dispose()
    command.upgrade(cfg, "head")
    assert _version(url) == HEAD


# ---------------------------------------------------------------- constraints (ORM on SQLite)


def test_tables_are_append_only_guarded() -> None:
    assert guarded_tables() >= MTM_TABLES


def test_unique_signal_date(db_session: Session) -> None:
    """11-PREMORTEM #4 / criterion 11.4: exactly one row per (signal, date)."""
    sid = _signal(db_session)
    db_session.add(_pnl(sid))
    db_session.commit()
    db_session.add(_pnl(sid, total_pnl_cents=5_000))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_total_check_rejects_mismatch(db_session: Session) -> None:
    """11-PREMORTEM #7."""
    sid = _signal(db_session)
    db_session.add(_pnl(sid, total_pnl_cents=5_001))
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize(
    "bad",
    [{"open_qty": -1}, {"open_cost_cents": -1}, {"mark_close_cents": 0}],
    ids=["neg-qty", "neg-cost", "zero-mark"],
)
def test_pnl_value_checks(db_session: Session, bad: dict) -> None:
    sid = _signal(db_session)
    db_session.add(_pnl(sid, **bad))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_negative_pnl_allowed(db_session: Session) -> None:
    sid = _signal(db_session)
    db_session.add(_pnl(sid, unrealized_pnl_cents=-7_000, total_pnl_cents=-7_000))
    db_session.commit()


def test_cash_event_activity_type_check(db_session: Session) -> None:
    db_session.add(_cash(activity_type="FILL"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_cash_event_unique_activity_id(db_session: Session) -> None:
    db_session.add(_cash())
    db_session.commit()
    db_session.add(_cash(net_amount_cents=1))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_withholding_can_be_negative(db_session: Session) -> None:
    db_session.add(_cash(broker_activity_id="w1", activity_type="DIVWH", net_amount_cents=-36))
    db_session.commit()


@pytest.mark.parametrize("op", ["update", "delete"])
def test_orm_guard_rejects_mutation(db_session: Session, op: str) -> None:
    """11-PREMORTEM #3 (L1): the session refuses UPDATE / DELETE."""
    sid = _signal(db_session)
    row = _pnl(sid)
    db_session.add(row)
    db_session.commit()
    if op == "update":
        row.total_pnl_cents = 1
    else:
        db_session.delete(row)
    with pytest.raises(AppendOnlyViolation):
        db_session.flush()


# --------------------------------------------------------------------------- PostgreSQL (L3)


@pytest.fixture(scope="module")
def pg_cfg() -> Iterator[tuple[Config, str]]:
    url = _pg_url_or_skip()
    previous = os.environ.get("DATABASE_URL")
    try:
        yield _alembic_config(url), url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.mark.slow
def test_pg_trigger_rejects_update(pg_cfg: tuple[Config, str]) -> None:
    """11-PREMORTEM #3 (L3): raw SQL UPDATE/DELETE is refused by the database."""
    cfg, url = pg_cfg
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        with Session(engine) as s:
            sid = _signal(s, ticker="PG7")
            s.add(_pnl(sid, ticker="PG7"))
            s.add(_cash(broker_activity_id=f"pg7-{sid}", ticker="PG7"))
            s.commit()
        for table in sorted(MTM_TABLES):
            with engine.begin() as conn, pytest.raises(DBAPIError) as exc:
                conn.execute(text(f"UPDATE {table} SET payload = payload"))  # noqa: S608
            assert "append-only" in str(exc.value)
            with engine.begin() as conn, pytest.raises(DBAPIError):
                conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    finally:
        engine.dispose()


@pytest.mark.slow
def test_pg_downgrade_007_keeps_shared_guard_function(pg_cfg: tuple[Config, str]) -> None:
    """007 reuses 004's guard function; its downgrade must drop only its own triggers."""
    cfg, url = pg_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "006")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            fn = conn.execute(
                text("SELECT count(*) FROM pg_proc WHERE proname = 'paper_append_only_guard'")
            ).scalar()
            trg = conn.execute(
                text(
                    "SELECT count(*) FROM pg_trigger WHERE tgname IN "
                    "('trg_paper_pnl_daily_append_only', 'trg_paper_cash_events_append_only')"
                )
            ).scalar()
        assert fn == 1, "downgrade 007 dropped the guard function 004 still needs"
        assert trg == 0
    finally:
        engine.dispose()
        command.upgrade(cfg, "head")
