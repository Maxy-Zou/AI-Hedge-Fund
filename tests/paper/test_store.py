"""Phase 9 -- paper.store insert paths and paper.records validation (PT-01..03)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai_hedge_fund.paper import (
    DuplicateFill,
    DuplicateSubmission,
    NewPaperFill,
    NewPaperTrade,
    PaperFillRecord,
    PaperTradeRecord,
    SignalNotFound,
    SignalTickerMismatch,
    SignalWrongRecordType,
    TradeNotFound,
    insert_paper_fill,
    insert_paper_trade,
)
from tests.paper.conftest import SHA, seed_signal


def _new_trade(signal_id: int, **overrides: Any) -> NewPaperTrade:
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
        "as_of_date": "2026-04-18",
        "payload": {"schema_version": 1, "final_signal": {"direction": "long"}},
    }
    fields.update(overrides)
    return NewPaperTrade(**fields)


def _new_fill(trade_id: int, **overrides: Any) -> NewPaperFill:
    fields: dict[str, Any] = {
        "trade_id": trade_id,
        "broker_fill_id": "fill-1",
        "filled_qty": 10,
        "fill_price_cents": 18_500_00,
        "filled_at": datetime(2026, 4, 18, 14, 30, tzinfo=UTC),
        "as_of_date": "2026-04-18",
        "payload": {"schema_version": 1},
    }
    fields.update(overrides)
    return NewPaperFill(**fields)


# --------------------------------------------------------------------------- trades


def test_insert_trade_returns_frozen_record(db_session: Session, signal_id: int) -> None:
    rec = insert_paper_trade(db_session, _new_trade(signal_id))
    assert isinstance(rec, PaperTradeRecord)
    assert rec.id >= 1 and rec.signal_id == signal_id and rec.attempt_no == 1
    assert rec.as_of_date == "2026-04-18T00:00:00+00:00"
    assert rec.observed_date  # populated by server_default and loaded back
    assert rec.payload["final_signal"]["direction"] == "long"
    with pytest.raises(ValidationError):
        rec.quantity = 1  # type: ignore[misc]


def test_insert_raises_signal_not_found(db_session: Session) -> None:
    with pytest.raises(SignalNotFound):
        insert_paper_trade(db_session, _new_trade(999_999))


@pytest.mark.parametrize("record_type", ["review", "outcome"])
def test_insert_raises_wrong_record_type(db_session: Session, record_type: str) -> None:
    """09-PREMORTEM #15: only analysis rows are signals."""
    sid = seed_signal(db_session, record_type=record_type)
    with pytest.raises(SignalWrongRecordType):
        insert_paper_trade(db_session, _new_trade(sid))


def test_insert_raises_ticker_mismatch(db_session: Session, signal_id: int) -> None:
    """09-PREMORTEM #14."""
    with pytest.raises(SignalTickerMismatch):
        insert_paper_trade(db_session, _new_trade(signal_id, ticker="MSFT"))


def test_same_signal_and_attempt_raises_duplicate(db_session: Session, signal_id: int) -> None:
    insert_paper_trade(db_session, _new_trade(signal_id, broker_order_id="a"))
    with pytest.raises(DuplicateSubmission):
        insert_paper_trade(db_session, _new_trade(signal_id, broker_order_id="b"))


def test_duplicate_broker_order_id_raises_duplicate(db_session: Session) -> None:
    a = seed_signal(db_session, ticker="AAPL")
    b = seed_signal(db_session, ticker="MSFT")
    insert_paper_trade(db_session, _new_trade(a, broker_order_id="same"))
    with pytest.raises(DuplicateSubmission):
        insert_paper_trade(db_session, _new_trade(b, ticker="MSFT", broker_order_id="same"))


def test_next_attempt_succeeds(db_session: Session, signal_id: int) -> None:
    """D4: deliberate retry after rejection is a new row."""
    insert_paper_trade(
        db_session, _new_trade(signal_id, submit_status="rejected", broker_order_id=None)
    )
    rec = insert_paper_trade(
        db_session, _new_trade(signal_id, attempt_no=2, broker_order_id="ord-2")
    )
    assert rec.attempt_no == 2


def test_session_usable_after_duplicate_submission(db_session: Session) -> None:
    """09-PREMORTEM #10: store must roll back so the next insert works."""
    a = seed_signal(db_session, ticker="AAPL")
    b = seed_signal(db_session, ticker="MSFT")
    insert_paper_trade(db_session, _new_trade(a, broker_order_id="x"))
    with pytest.raises(DuplicateSubmission):
        insert_paper_trade(db_session, _new_trade(a, broker_order_id="y"))
    rec = insert_paper_trade(db_session, _new_trade(b, ticker="MSFT", broker_order_id="z"))
    assert rec.ticker == "MSFT"


# --------------------------------------------------------------------------- fills


def test_insert_fill_returns_frozen_record(db_session: Session, signal_id: int) -> None:
    trade = insert_paper_trade(db_session, _new_trade(signal_id))
    rec = insert_paper_fill(db_session, _new_fill(trade.id))
    assert isinstance(rec, PaperFillRecord)
    assert rec.trade_id == trade.id and rec.filled_qty == 10
    assert rec.filled_at == "2026-04-18T14:30:00+00:00"
    assert rec.observed_date


def test_insert_fill_raises_trade_not_found(db_session: Session) -> None:
    with pytest.raises(TradeNotFound):
        insert_paper_fill(db_session, _new_fill(999_999))


def test_duplicate_fill_raises_and_session_usable(db_session: Session, signal_id: int) -> None:
    trade = insert_paper_trade(db_session, _new_trade(signal_id))
    insert_paper_fill(db_session, _new_fill(trade.id, broker_fill_id="f"))
    with pytest.raises(DuplicateFill):
        insert_paper_fill(db_session, _new_fill(trade.id, broker_fill_id="f"))
    rec = insert_paper_fill(db_session, _new_fill(trade.id, broker_fill_id="g", filled_qty=1))
    assert rec.broker_fill_id == "g"


def test_naive_filled_at_is_treated_as_utc(db_session: Session, signal_id: int) -> None:
    trade = insert_paper_trade(db_session, _new_trade(signal_id))
    rec = insert_paper_fill(db_session, _new_fill(trade.id, filled_at=datetime(2026, 4, 18, 9, 0)))
    assert rec.filled_at == "2026-04-18T09:00:00+00:00"


# --------------------------------------------------------------------------- input validation


@pytest.mark.parametrize(
    "bad",
    [
        {"order_type": "limit", "limit_price_cents": None},
        {"order_type": "market", "limit_price_cents": 100_00},
        {"submit_status": "submitted", "broker_order_id": None},
        {"submit_status": "rejected", "broker_order_id": "x"},
        {"submit_status": "refused_veto", "broker_order_id": "x"},
        {"quantity": 0},
        {"quantity": 10.5},
        {"quantity": 10.0},  # strict: floats never coerce for money/qty (#18)
        {"limit_price_cents": -1, "order_type": "limit"},
        {"limit_price_cents": 1.5, "order_type": "limit"},
        {"attempt_no": 0},
        {"side": "long"},
        {"policy_sha": "short"},
        {"ticker": ""},
        {"unexpected": 1},  # extra=forbid
    ],
    ids=lambda d: "+".join(f"{k}={v}" for k, v in d.items()),
)
def test_new_trade_rejects(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _new_trade(1, **bad)


@pytest.mark.parametrize(
    "key", ["api_key", "API_KEY", "secret", "client_secret", "access_token", "password", "Token"]
)
def test_payload_rejects_secret_like_keys(key: str) -> None:
    """09-PREMORTEM #17 tripwire (top-level keys only)."""
    with pytest.raises(ValidationError, match="secret"):
        _new_trade(1, payload={"schema_version": 1, key: "abc"})


def test_payload_allows_idempotency_key_and_nested_keys() -> None:
    """'idempotency_key' is not a secret; nested keys are Phase 10's job to redact."""
    t = _new_trade(1, payload={"idempotency_key": "sig-1", "broker": {"token": "x"}})
    assert t.payload["idempotency_key"] == "sig-1"


@pytest.mark.parametrize(
    "bad",
    [
        {"filled_qty": 0},
        {"filled_qty": 2.0},
        {"fill_price_cents": 0},
        {"fill_price_cents": -1},
        {"fill_price_cents": 1.0},
        {"broker_fill_id": ""},
        {"nope": 1},
    ],
    ids=lambda d: "+".join(f"{k}={v}" for k, v in d.items()),
)
def test_new_fill_rejects(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _new_fill(1, **bad)


def test_records_are_frozen_and_forbid_extra() -> None:
    for model in (NewPaperTrade, NewPaperFill, PaperTradeRecord, PaperFillRecord):
        assert model.model_config.get("frozen") is True
        assert model.model_config.get("extra") == "forbid"
