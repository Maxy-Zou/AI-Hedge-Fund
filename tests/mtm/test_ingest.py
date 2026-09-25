"""Phase 11 T4 -- ingest broker activities into paper_fills / paper_cash_events (D1, A1)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import PaperCashEvent, PaperFill
from ai_hedge_fund.execution.broker import BrokerActivity, RejectedActivity
from ai_hedge_fund.mtm.ingest import IngestResult, ingest_activities
from ai_hedge_fund.paper import query_paper_fills
from ai_hedge_fund.paper.records import NewPaperTrade
from ai_hedge_fund.paper.store import insert_paper_trade
from tests.execution.fakes import FakeBroker
from tests.paper.conftest import seed_signal

SHA = "d" * 64
SINCE = date(2026, 9, 1)


def _trade(
    session: Session, broker_order_id: str, *, side: str = "buy", ticker: str = "AAPL"
) -> int:
    sid = seed_signal(session, ticker=ticker)
    rec = insert_paper_trade(
        session,
        NewPaperTrade(
            signal_id=sid,
            ticker=ticker,
            side=side,
            order_type="market",
            quantity=10,
            submit_status="submitted",
            broker_order_id=broker_order_id,
            risk_status_at_submit="APPROVED",
            policy_sha=SHA,
            review_policy_sha=SHA,
            as_of_date="2026-09-01",
            payload={"schema_version": 1},
        ),
    )
    return rec.id


def _fill(
    n: int,
    order_id: str = "ord-1",
    *,
    qty: int = 5,
    price: int = 18_725,
    at: datetime = datetime(2026, 9, 2, 14, 30, tzinfo=UTC),
    side: str = "buy",
    symbol: str = "AAPL",
) -> BrokerActivity:
    return BrokerActivity(
        activity_id=f"act-fill-{n}",
        activity_type="FILL",
        symbol=symbol,
        occurred_at=at,
        broker_order_id=order_id,
        side=side,  # type: ignore[arg-type]
        qty=qty,
        price_cents=price,
        net_amount_cents=None,
        raw={"id": f"act-fill-{n}", "order_id": order_id},
    )


def _cash(
    n: int, activity_type: str = "DIV", net: int = 240, symbol: str = "AAPL"
) -> BrokerActivity:
    return BrokerActivity(
        activity_id=f"act-{activity_type.lower()}-{n}",
        activity_type=activity_type,
        symbol=symbol,
        occurred_at=datetime(2026, 9, 15, 4, 0, tzinfo=UTC),
        broker_order_id=None,
        side=None,
        qty=None,
        price_cents=None,
        net_amount_cents=net,
        raw={"id": f"act-{n}"},
    )


def _broker(*activities: BrokerActivity) -> FakeBroker:
    broker = FakeBroker()
    broker.activities.extend(activities)
    return broker


def _count(session: Session, model: type) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_partial_fills_one_row_each(db_session: Session) -> None:
    """11-PREMORTEM #18: each execution is its own row with its own price."""
    tid = _trade(db_session, "ord-1")
    broker = _broker(_fill(1, qty=4, price=18_700), _fill(2, qty=6, price=18_750))
    result = ingest_activities(db_session, broker, SINCE)
    assert result.fills_inserted == 2
    fills = query_paper_fills(db_session, trade_id=tid, as_of_date="2099-01-01")
    assert sorted((f.filled_qty, f.fill_price_cents) for f in fills) == [(4, 18_700), (6, 18_750)]


def test_rerun_inserts_nothing(db_session: Session) -> None:
    _trade(db_session, "ord-1")
    broker = _broker(_fill(1), _cash(1))
    ingest_activities(db_session, broker, SINCE)
    again = ingest_activities(db_session, broker, SINCE)
    assert again == IngestResult(fills_skipped_duplicate=1, cash_skipped_duplicate=1)
    assert (_count(db_session, PaperFill), _count(db_session, PaperCashEvent)) == (1, 1)


def test_unknown_order_skipped_and_logged(db_session: Session) -> None:
    """11-PREMORTEM #33: a manual trade's fill is skipped with a warning, not guessed."""
    _trade(db_session, "ord-1")
    with structlog.testing.capture_logs() as logs:
        result = ingest_activities(db_session, _broker(_fill(1, order_id="manual-9")), SINCE)
    assert result.fills_skipped_unknown_order == 1 and result.fills_inserted == 0
    assert any(
        e["event"] == "fill_unknown_order" and e["broker_order_id"] == "manual-9" for e in logs
    )


@pytest.mark.parametrize(
    "fill",
    [_fill(1, side="sell"), _fill(1, symbol="MSFT")],
    ids=["side", "symbol"],
)
def test_fill_disagreeing_with_its_trade_is_skipped(
    db_session: Session, fill: BrokerActivity
) -> None:
    _trade(db_session, "ord-1")
    with structlog.testing.capture_logs() as logs:
        result = ingest_activities(db_session, _broker(fill), SINCE)
    assert result.fills_skipped_mismatch == 1 and _count(db_session, PaperFill) == 0
    assert any(e["event"] == "fill_trade_mismatch" and e["log_level"] == "error" for e in logs)


def test_fill_as_of_is_new_york_date(db_session: Session) -> None:
    """11-PREMORTEM #11: a 20:30 ET fill (00:30Z next day) belongs to the NY date."""
    tid = _trade(db_session, "ord-1")
    late = datetime(2026, 9, 3, 0, 30, tzinfo=UTC)
    ingest_activities(db_session, _broker(_fill(1, at=late)), SINCE)
    [fill] = query_paper_fills(db_session, trade_id=tid, as_of_date="2099-01-01")
    assert fill.as_of_date.startswith("2026-09-02")
    assert fill.filled_at.startswith("2026-09-03T00:30")


def test_dividend_and_withholding_stored(db_session: Session) -> None:
    broker = _broker(_cash(1), _cash(2, "DIVWH", net=-36))
    result = ingest_activities(db_session, broker, SINCE)
    assert result.cash_inserted == 2
    rows = db_session.scalars(select(PaperCashEvent).order_by(PaperCashEvent.id)).all()
    assert [(r.activity_type, r.net_amount_cents) for r in rows] == [("DIV", 240), ("DIVWH", -36)]
    assert rows[0].event_date == date(2026, 9, 15)


def test_split_activity_stored_with_zero_amount(db_session: Session) -> None:
    """11-PREMORTEM #14 (ingest half): corporate actions are recorded so the job can detect them."""
    ingest_activities(db_session, _broker(_cash(1, "SPLIT", net=0)), SINCE)
    [row] = db_session.scalars(select(PaperCashEvent)).all()
    assert (row.activity_type, row.net_amount_cents) == ("SPLIT", 0)


def test_payload_is_the_redacted_raw(db_session: Session) -> None:
    """11-PREMORTEM #32: what is stored is the adapter's redacted raw, account_id already gone."""
    tid = _trade(db_session, "ord-1")
    ingest_activities(db_session, _broker(_fill(1)), SINCE)
    [fill] = query_paper_fills(db_session, trade_id=tid, as_of_date="2099-01-01")
    assert fill.payload == {"id": "act-fill-1", "order_id": "ord-1"}


def test_requests_fills_and_every_cash_type(db_session: Session) -> None:
    seen: list[tuple[tuple[str, ...], date]] = []

    class Spy(FakeBroker):
        def list_activities(self, types, since):  # noqa: ANN001, ANN202
            seen.append((tuple(types), since))
            return super().list_activities(types, since)

    ingest_activities(db_session, Spy(), SINCE)
    [(types, since)] = seen
    assert since == SINCE
    assert set(types) == {
        "FILL", "DIV", "DIVCGL", "DIVCGS", "DIVNRA", "DIVROC", "DIVTXEX", "DIVWH",
        "SPLIT", "SPIN", "MA", "NC",
    }  # fmt: skip


# --------------------------------------------------------------------------- review H2


def _rejected(order_id: str | None, kind: str = "FILL") -> RejectedActivity:
    return RejectedActivity(
        activity_id=f"rej-{order_id}", activity_type=kind, order_id=order_id,
        reason="fractional qty 0.5", raw={},
    )  # fmt: skip


def test_rejected_foreign_fill_is_skipped_and_the_rest_ingested(db_session: Session) -> None:
    _trade(db_session, "ord-1")
    broker = _broker(_fill(1))
    broker.rejected.append(_rejected("manual-9"))
    with structlog.testing.capture_logs() as logs:
        result = ingest_activities(db_session, broker, SINCE)
    assert (result.fills_inserted, result.fills_skipped_unusable, result.fills_rejected_ours) == (
        1, 1, 0,
    )  # fmt: skip
    assert any(e["event"] == "activity_rejected" and e["log_level"] == "warning" for e in logs)


def test_rejected_fill_for_our_order_is_an_error(db_session: Session) -> None:
    _trade(db_session, "ord-1")
    broker = _broker()
    broker.rejected.append(_rejected("ord-1"))
    with structlog.testing.capture_logs() as logs:
        result = ingest_activities(db_session, broker, SINCE)
    assert result.fills_rejected_ours == 1
    assert any(e["event"] == "own_fill_rejected" and e["log_level"] == "error" for e in logs)


def test_rejected_cash_activity_is_counted(db_session: Session) -> None:
    broker = _broker()
    broker.rejected.append(_rejected(None, kind="DIV"))
    assert ingest_activities(db_session, broker, SINCE).cash_skipped_unusable == 1
