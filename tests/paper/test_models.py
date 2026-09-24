"""Phase 9 -- paper_trades / paper_fills schema tests (PT-01..04).

Runs on the in-memory SQLite fixture from tests/conftest.py, which builds
tables via ``Base.metadata.create_all``. The very first test is the guard
that makes every later foreign-key assertion meaningful: SQLite silently
ignores FOREIGN KEY unless ``PRAGMA foreign_keys`` is on
(09-PREMORTEM.md #1). ORM/migration parity is proven separately in
test_migration_roundtrip.py (#11).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import EpisodicMemory, PaperFill, PaperTrade

SHA = "a" * 64
AS_OF = normalise_as_of("2026-04-18")


def _seed_signal(db_session: Session, ticker: str = "AAPL") -> int:
    """Insert one record_type='analysis' episodic row and return its id (FK target)."""
    row = EpisodicMemory(
        ticker=ticker,
        sector="Technology",
        record_type="analysis",
        signal_direction="long",
        confidence=70,
        policy_sha=SHA,
        as_of_date=AS_OF,
        payload={"schema_version": 1},
    )
    db_session.add(row)
    db_session.commit()
    return row.id


def _trade(signal_id: int, **overrides: Any) -> PaperTrade:
    """A valid submitted market order; override any field to make it invalid."""
    fields: dict[str, Any] = {
        "signal_id": signal_id,
        "ticker": "AAPL",
        "side": "buy",
        "order_type": "market",
        "quantity": 10,
        "submit_status": "submitted",
        "broker_order_id": "ord-1",
        "risk_status_at_submit": "APPROVED",
        "policy_sha": SHA,
        "review_policy_sha": SHA,
        "as_of_date": AS_OF,
        "payload": {"schema_version": 1},
    }
    fields.update(overrides)
    return PaperTrade(**fields)


def _fill(trade_id: int, **overrides: Any) -> PaperFill:
    fields: dict[str, Any] = {
        "trade_id": trade_id,
        "broker_fill_id": "fill-1",
        "filled_qty": 10,
        "fill_price_cents": 18_500_00,
        "filled_at": datetime(2026, 4, 18, 14, 30, tzinfo=UTC),
        "as_of_date": AS_OF,
        "payload": {"schema_version": 1},
    }
    fields.update(overrides)
    return PaperFill(**fields)


def _assert_rejected(db_session: Session, obj: Any) -> None:
    db_session.add(obj)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------- guard


def test_sqlite_fk_pragma_enabled(sqlite_engine: Engine) -> None:
    """09-PREMORTEM #1 guard: FK enforcement must be ON for the fixture engine.

    If this fails, every ``IntegrityError`` assertion on a foreign key in this
    suite is vacuous and PT-03 is unproven.
    """
    with sqlite_engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


# --------------------------------------------------------------------------- shape


def test_tables_and_named_constraints_exist(sqlite_engine: Engine) -> None:
    insp = inspect(sqlite_engine)
    assert {"paper_trades", "paper_fills"} <= set(insp.get_table_names())

    trade_uniques = {u["name"] for u in insp.get_unique_constraints("paper_trades")}
    assert {"uq_paper_trades_signal_attempt", "uq_paper_trades_broker_order_id"} <= trade_uniques
    trade_indexes = {i["name"] for i in insp.get_indexes("paper_trades")}
    assert {"ix_paper_trades_signal_id", "ix_paper_trades_ticker_asof"} <= trade_indexes

    fill_uniques = {u["name"] for u in insp.get_unique_constraints("paper_fills")}
    assert "uq_paper_fills_broker_fill_id" in fill_uniques
    fill_indexes = {i["name"] for i in insp.get_indexes("paper_fills")}
    assert {"ix_paper_fills_trade_id", "ix_paper_fills_asof"} <= fill_indexes


def test_valid_trade_and_fill_round_trip(db_session: Session) -> None:
    sid = _seed_signal(db_session)
    trade = _trade(sid)
    db_session.add(trade)
    db_session.commit()
    assert trade.id is not None
    assert trade.attempt_no == 1  # default

    fill = _fill(trade.id)
    db_session.add(fill)
    db_session.commit()
    assert fill.id is not None
    assert fill.trade_id == trade.id


# --------------------------------------------------------------------------- 9.3 timestamps


def test_as_of_date_required(db_session: Session) -> None:
    sid = _seed_signal(db_session)
    _assert_rejected(db_session, _trade(sid, as_of_date=None))


def test_observed_date_server_default_and_not_nullable(db_session: Session) -> None:
    """09-PREMORTEM #23: observed_date must be populated by the DB and NOT NULL."""
    sid = _seed_signal(db_session)
    trade = _trade(sid)
    db_session.add(trade)
    db_session.commit()
    db_session.refresh(trade)
    assert trade.observed_date is not None
    col = PaperTrade.__table__.c.observed_date
    assert col.nullable is False
    assert col.server_default is not None
    assert PaperFill.__table__.c.observed_date.nullable is False


# --------------------------------------------------------------------------- 9.4 foreign keys


def test_fk_rejects_unknown_signal(db_session: Session) -> None:
    _assert_rejected(db_session, _trade(signal_id=999_999))


def test_fk_rejects_fill_for_unknown_trade(db_session: Session) -> None:
    _assert_rejected(db_session, _fill(trade_id=999_999))


# --------------------------------------------------------------------------- uniques


def test_refusal_statuses_accepted(db_session: Session) -> None:
    """Phase 10 migration 005: refused_review / refused_policy are valid statuses."""
    for status in ("refused_veto", "refused_review", "refused_policy"):
        sid = _seed_signal(db_session, f"T{status[-4:]}")
        db_session.add(
            _trade(sid, ticker=f"T{status[-4:]}", submit_status=status, broker_order_id=None)
        )
        db_session.commit()


def test_same_signal_and_attempt_is_rejected(db_session: Session) -> None:
    """D4: (signal_id, attempt_no) is the idempotency grain."""
    sid = _seed_signal(db_session)
    db_session.add(_trade(sid, broker_order_id="ord-a"))
    db_session.commit()
    _assert_rejected(db_session, _trade(sid, broker_order_id="ord-b"))


def test_next_attempt_for_same_signal_is_allowed(db_session: Session) -> None:
    """D4: a deliberate retry is a new immutable row, not an update."""
    sid = _seed_signal(db_session)
    db_session.add(_trade(sid, submit_status="rejected", broker_order_id=None))
    db_session.commit()
    db_session.add(_trade(sid, attempt_no=2, broker_order_id="ord-2"))
    db_session.commit()
    assert db_session.query(PaperTrade).filter_by(signal_id=sid).count() == 2


def test_broker_order_id_unique(db_session: Session) -> None:
    sid_a = _seed_signal(db_session, "AAPL")
    sid_b = _seed_signal(db_session, "MSFT")
    db_session.add(_trade(sid_a, broker_order_id="dup"))
    db_session.commit()
    _assert_rejected(db_session, _trade(sid_b, ticker="MSFT", broker_order_id="dup"))


def test_broker_fill_id_unique(db_session: Session) -> None:
    sid = _seed_signal(db_session)
    trade = _trade(sid)
    db_session.add(trade)
    db_session.commit()
    db_session.add(_fill(trade.id, broker_fill_id="f-dup"))
    db_session.commit()
    _assert_rejected(db_session, _fill(trade.id, broker_fill_id="f-dup"))


# --------------------------------------------------------------------------- CHECK constraints


@pytest.mark.parametrize(
    "bad",
    [
        {"attempt_no": 0},
        {"quantity": 0},
        {"quantity": -5},
        {"side": "long"},
        {"order_type": "stop"},
        {"submit_status": "filled"},
        # limit price present iff limit order
        {"order_type": "limit", "limit_price_cents": None},
        {"order_type": "market", "limit_price_cents": 100_00},
        # broker id present iff submitted
        {"submit_status": "submitted", "broker_order_id": None},
        {"submit_status": "rejected", "broker_order_id": "ord-x"},
        {"submit_status": "refused_veto", "broker_order_id": "ord-y"},
    ],
    ids=lambda d: "+".join(f"{k}={v}" for k, v in d.items()),
)
def test_trade_check_constraints(db_session: Session, bad: dict[str, Any]) -> None:
    sid = _seed_signal(db_session)
    _assert_rejected(db_session, _trade(sid, **bad))


def test_limit_order_with_price_is_valid(db_session: Session) -> None:
    sid = _seed_signal(db_session)
    db_session.add(_trade(sid, order_type="limit", limit_price_cents=180_00))
    db_session.commit()


@pytest.mark.parametrize(
    "bad",
    [{"filled_qty": 0}, {"filled_qty": -1}, {"fill_price_cents": 0}, {"fill_price_cents": -1}],
    ids=lambda d: "+".join(f"{k}={v}" for k, v in d.items()),
)
def test_fill_check_constraints(db_session: Session, bad: dict[str, Any]) -> None:
    sid = _seed_signal(db_session)
    trade = _trade(sid)
    db_session.add(trade)
    db_session.commit()
    _assert_rejected(db_session, _fill(trade.id, **bad))


# --------------------------------------------------------------------------- NOT NULL sweep


@pytest.mark.parametrize(
    "column",
    [
        "ticker",
        "side",
        "order_type",
        "quantity",
        "submit_status",
        "risk_status_at_submit",
        "policy_sha",
        "review_policy_sha",
        "payload",
    ],
)
def test_trade_required_columns(db_session: Session, column: str) -> None:
    sid = _seed_signal(db_session)
    _assert_rejected(db_session, _trade(sid, **{column: None}))


@pytest.mark.parametrize(
    "column", ["broker_fill_id", "filled_qty", "fill_price_cents", "filled_at", "payload"]
)
def test_fill_required_columns(db_session: Session, column: str) -> None:
    sid = _seed_signal(db_session)
    trade = _trade(sid)
    db_session.add(trade)
    db_session.commit()
    _assert_rejected(db_session, _fill(trade.id, **{column: None}))
