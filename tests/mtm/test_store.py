"""Phase 11 T3 -- mtm records + append-only store (11-SPEC s3)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import get_args

import pytest
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import CASH_ACTIVITY_TYPES, PaperCashEvent, PaperPnlDaily
from ai_hedge_fund.mtm import store
from ai_hedge_fund.mtm.errors import ConcurrentRun
from ai_hedge_fund.mtm.records import CashActivityType, NewCashEvent, NewPnlRow
from tests.paper.conftest import seed_signal

SHA = "f" * 64


def _row(signal_id: int, day: int = 2, **overrides: object) -> NewPnlRow:
    values: dict = {
        "signal_id": signal_id,
        "pnl_date": date(2026, 9, day),
        "ticker": "AAPL",
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
    }
    return NewPnlRow(**{**values, **overrides})


def _cash(**overrides: object) -> NewCashEvent:
    values: dict = {
        "broker_activity_id": "20260902::a",
        "activity_type": "DIV",
        "ticker": "AAPL",
        "event_date": date(2026, 9, 2),
        "net_amount_cents": 240,
        "payload": {"id": "20260902::a"},
    }
    return NewCashEvent(**{**values, **overrides})


def _count(session: Session, model: type) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


@pytest.fixture()
def statements(db_session: Session) -> Iterator[list[str]]:
    """Every SQL statement the session's engine executes during the test."""
    seen: list[str] = []
    engine = db_session.get_bind()

    def _record(conn, cursor, statement, params, context, executemany) -> None:  # noqa: ANN001
        seen.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", _record)


# --------------------------------------------------------------------------- records


def test_pnl_total_must_equal_parts() -> None:
    with pytest.raises(ValidationError, match="total_pnl_cents"):
        _row(1, total_pnl_cents=5_001)


@pytest.mark.parametrize("field", ["open_cost_cents", "unrealized_pnl_cents", "mark_close_cents"])
def test_pnl_money_is_strict_int(field: str) -> None:
    with pytest.raises(ValidationError):
        _row(1, **{field: 10.5})


def test_pnl_payload_rejects_secret_keys() -> None:
    with pytest.raises(ValidationError, match="secret"):
        _row(1, payload={"api_key": "x"})


def test_cash_non_cash_action_must_be_zero() -> None:
    with pytest.raises(ValidationError, match="SPLIT"):
        _cash(activity_type="SPLIT", net_amount_cents=5)
    assert _cash(activity_type="SPLIT", net_amount_cents=0).net_amount_cents == 0


def test_cash_activity_types_match_db_check() -> None:
    """The record Literal and the DB CHECK list are two spellings of one set."""
    assert set(get_args(CashActivityType)) == set(CASH_ACTIVITY_TYPES)


def test_cash_rejects_fill_type() -> None:
    with pytest.raises(ValidationError):
        _cash(activity_type="FILL")


# --------------------------------------------------------------------------- pnl store


def test_insert_pnl_rows_appends_and_returns_records(db_session: Session) -> None:
    sid = seed_signal(db_session)
    result = store.insert_pnl_rows(db_session, [_row(sid, 2), _row(sid, 3)])
    assert (result.inserted, result.skipped_existing) == (2, 0)
    assert _count(db_session, PaperPnlDaily) == 2
    rec = store.query_pnl_rows(db_session, signal_id=sid)
    assert [r.pnl_date for r in rec] == ["2026-09-02", "2026-09-03"]
    assert rec[0].as_of_date.startswith("2026-09-02")


def test_rerun_skips_existing_and_issues_no_update(
    db_session: Session, statements: list[str]
) -> None:
    """11-PREMORTEM #3 / criterion 11.2: skip-or-insert, never UPDATE."""
    sid = seed_signal(db_session)
    store.insert_pnl_rows(db_session, [_row(sid, 2)])
    statements.clear()
    result = store.insert_pnl_rows(
        db_session, [_row(sid, 2, unrealized_pnl_cents=9, total_pnl_cents=9), _row(sid, 3)]
    )
    assert (result.inserted, result.skipped_existing) == (1, 1)
    assert not {"UPDATE", "DELETE"} & set(statements)
    first = store.query_pnl_rows(db_session, signal_id=sid)[0]
    assert first.total_pnl_cents == 5_000  # the original row, untouched


def test_duplicate_pair_within_batch_rejected(db_session: Session) -> None:
    sid = seed_signal(db_session)
    with pytest.raises(ValueError, match="duplicate"):
        store.insert_pnl_rows(db_session, [_row(sid, 2), _row(sid, 2)])
    assert _count(db_session, PaperPnlDaily) == 0


def test_unique_violation_rolls_back_whole_batch(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """11-PREMORTEM #6: a concurrent writer's row makes the batch fail whole, not half."""
    sid = seed_signal(db_session)
    store.insert_pnl_rows(db_session, [_row(sid, 3)])
    # Simulate the race: our existence check ran before the other run committed.
    monkeypatch.setattr(store, "_existing_keys", lambda *_a, **_k: set())
    with pytest.raises(ConcurrentRun):
        store.insert_pnl_rows(db_session, [_row(sid, 2), _row(sid, 3), _row(sid, 4)])
    assert _count(db_session, PaperPnlDaily) == 1
    assert store.insert_pnl_rows(db_session, [_row(sid, 5)]).inserted == 1  # session usable


def test_empty_batch_is_noop(db_session: Session) -> None:
    assert store.insert_pnl_rows(db_session, []) == store.InsertResult(0, 0)


# --------------------------------------------------------------------------- cash store


def test_insert_cash_event_and_duplicate_returns_none(db_session: Session) -> None:
    rec = store.insert_cash_event(db_session, _cash())
    assert rec is not None and rec.net_amount_cents == 240
    assert store.insert_cash_event(db_session, _cash(net_amount_cents=1)) is None
    assert _count(db_session, PaperCashEvent) == 1
    assert store.insert_cash_event(db_session, _cash(broker_activity_id="b")) is not None


def test_query_cash_events_filters_ticker_and_date(db_session: Session) -> None:
    store.insert_cash_event(db_session, _cash(broker_activity_id="a1"))
    store.insert_cash_event(db_session, _cash(broker_activity_id="a2", ticker="MSFT"))
    store.insert_cash_event(
        db_session, _cash(broker_activity_id="a3", event_date=date(2026, 9, 30))
    )
    got = store.query_cash_events(db_session, ticker="AAPL", on_or_before=date(2026, 9, 10))
    assert [e.broker_activity_id for e in got] == ["a1"]
