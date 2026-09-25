"""Ingest broker account activities into the paper ledger (Phase 11, D1 + A1).

FILL -> ``paper_fills`` via :func:`insert_paper_fill`, joined to our own
``paper_trades`` row by ``broker_order_id``. A fill for an order we never placed
(a manual trade) is skipped with a warning -- never attached to a guessed trade
(11-PREMORTEM #33). A fill whose symbol or side contradicts its trade is data
corruption: skipped and logged at error level, counted separately.

Dividend and corporate-action activities -> ``paper_cash_events`` for every
ticker (the EOD job filters). Both paths are idempotent through the tables'
unique broker ids, so re-running over the same window inserts nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import trading_date
from ai_hedge_fund.db.models import CASH_ACTIVITY_TYPES, PaperTrade
from ai_hedge_fund.execution.broker import BrokerActivity, BrokerClient
from ai_hedge_fund.mtm.records import NON_CASH_ACTIVITY_TYPES, NewCashEvent
from ai_hedge_fund.mtm.store import insert_cash_event
from ai_hedge_fund.paper.errors import DuplicateFill
from ai_hedge_fund.paper.records import NewPaperFill
from ai_hedge_fund.paper.store import insert_paper_fill

logger = structlog.get_logger(__name__)

ACTIVITY_TYPES: tuple[str, ...] = ("FILL", *CASH_ACTIVITY_TYPES)


@dataclass(frozen=True)
class IngestResult:
    fills_inserted: int = 0
    fills_skipped_duplicate: int = 0
    fills_skipped_unknown_order: int = 0
    fills_skipped_mismatch: int = 0
    cash_inserted: int = 0
    cash_skipped_duplicate: int = 0


_FILL_OUTCOMES = {
    "inserted": "fills_inserted",
    "duplicate": "fills_skipped_duplicate",
    "unknown_order": "fills_skipped_unknown_order",
    "mismatch": "fills_skipped_mismatch",
}


def _our_trade(db_session: Session, broker_order_id: str | None) -> PaperTrade | None:
    if broker_order_id is None:
        return None
    return db_session.scalars(
        select(PaperTrade).where(
            PaperTrade.broker_order_id == broker_order_id,
            PaperTrade.submit_status == "submitted",
        )
    ).one_or_none()


def _ingest_fill(db_session: Session, act: BrokerActivity) -> str:
    trade = _our_trade(db_session, act.broker_order_id)
    if trade is None:
        logger.warning(
            "fill_unknown_order",
            activity_id=act.activity_id,
            broker_order_id=act.broker_order_id,
            symbol=act.symbol,
        )
        return "unknown_order"
    if (trade.ticker, trade.side) != (act.symbol, act.side):
        logger.error(
            "fill_trade_mismatch",
            activity_id=act.activity_id,
            trade_id=trade.id,
            trade=(trade.ticker, trade.side),
            fill=(act.symbol, act.side),
        )
        return "mismatch"
    new = NewPaperFill(
        trade_id=trade.id,
        broker_fill_id=act.activity_id,
        filled_qty=act.qty,  # type: ignore[arg-type]  # FILL rows always carry qty/price
        fill_price_cents=act.price_cents,  # type: ignore[arg-type]
        filled_at=act.occurred_at,
        as_of_date=trading_date(act.occurred_at),
        payload=act.raw,
    )
    try:
        insert_paper_fill(db_session, new)
    except DuplicateFill:
        return "duplicate"
    return "inserted"


def _ingest_cash(db_session: Session, act: BrokerActivity) -> bool:
    """True if inserted, False if the activity id was already recorded."""
    non_cash = act.activity_type in NON_CASH_ACTIVITY_TYPES
    new = NewCashEvent(
        broker_activity_id=act.activity_id,
        activity_type=act.activity_type,  # type: ignore[arg-type]
        ticker=act.symbol,
        event_date=trading_date(act.occurred_at),
        net_amount_cents=0 if non_cash else (act.net_amount_cents or 0),
        payload=act.raw,
    )
    return insert_cash_event(db_session, new) is not None


def ingest_activities(db_session: Session, broker: BrokerClient, since: date) -> IngestResult:
    """Pull every fill and cash activity since New York date ``since`` and append it."""
    counts = dict.fromkeys(IngestResult.__dataclass_fields__, 0)
    for act in broker.list_activities(ACTIVITY_TYPES, since):
        if act.activity_type == "FILL":
            counts[_FILL_OUTCOMES[_ingest_fill(db_session, act)]] += 1
        elif _ingest_cash(db_session, act):
            counts["cash_inserted"] += 1
        else:
            counts["cash_skipped_duplicate"] += 1
    result = IngestResult(**counts)
    logger.info("ingest_activities_complete", since=str(since), **counts)
    return result
