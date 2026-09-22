"""Temporal recall over the paper-trading ledger (PT-05).

Every query filters ``as_of_date <= target`` through
:func:`ai_hedge_fund.db.dates.normalise_as_of`, the single chokepoint that
keeps the comparison stable on SQLite and PostgreSQL. A row dated exactly
``target`` **is** returned (``<=``, not ``<``; 09-PREMORTEM.md #6).

Unlike :func:`ai_hedge_fund.memory.recall.query_episodic`, which ORs its
``ticker`` / ``sector`` predicates to widen context, ``ticker`` and
``signal_id`` here AND together: a trade query narrows.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import PaperFill, PaperTrade
from ai_hedge_fund.paper.records import PaperFillRecord, PaperTradeRecord
from ai_hedge_fund.paper.store import to_fill_record, to_trade_record


def _check_limit(limit: int) -> None:
    """SQLite treats ``LIMIT -1`` as unbounded; PostgreSQL raises. Fail early on both."""
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")


def query_paper_trades(
    db_session: Session,
    *,
    as_of_date: str | date | datetime,
    ticker: str | None = None,
    signal_id: int | None = None,
    limit: int = 50,
) -> list[PaperTradeRecord]:
    """Trades visible as of ``as_of_date``, newest first.

    At least one of ``ticker`` / ``signal_id`` is required (Pitfall-8 DoS
    guard, mirroring memory recall). When both are given they AND.

    Raises:
        ValueError: neither ``ticker`` nor ``signal_id`` supplied.
    """
    if ticker is None and signal_id is None:
        raise ValueError("query_paper_trades requires ticker or signal_id")
    _check_limit(limit)
    target = normalise_as_of(as_of_date)
    q = db_session.query(PaperTrade).filter(PaperTrade.as_of_date <= target)
    if ticker is not None:
        q = q.filter(PaperTrade.ticker == ticker)
    if signal_id is not None:
        q = q.filter(PaperTrade.signal_id == signal_id)
    rows = q.order_by(PaperTrade.as_of_date.desc(), PaperTrade.id.desc()).limit(limit).all()
    return [to_trade_record(r) for r in rows]


def query_paper_fills(
    db_session: Session,
    *,
    as_of_date: str | date | datetime,
    trade_id: int | None = None,
    limit: int = 200,
) -> list[PaperFillRecord]:
    """Fills visible as of ``as_of_date``, newest first; optionally for one trade."""
    _check_limit(limit)
    target = normalise_as_of(as_of_date)
    q = db_session.query(PaperFill).filter(PaperFill.as_of_date <= target)
    if trade_id is not None:
        q = q.filter(PaperFill.trade_id == trade_id)
    rows = q.order_by(PaperFill.as_of_date.desc(), PaperFill.id.desc()).limit(limit).all()
    return [to_fill_record(r) for r in rows]
