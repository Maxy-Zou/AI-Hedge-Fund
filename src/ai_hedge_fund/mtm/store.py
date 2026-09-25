"""Append-only writers and readers for the mark-to-market tables (11-SPEC s3, D6).

``insert_pnl_rows`` is skip-or-insert: pairs already present are skipped, the
rest go in one transaction, and nothing is ever updated (MTM-04, criterion
11.2). If another run commits a colliding pair between our existence check and
our commit, the whole batch rolls back and :class:`ConcurrentRun` is raised --
a day is never half-written (11-PREMORTEM #6).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import NamedTuple

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import PaperCashEvent, PaperPnlDaily
from ai_hedge_fund.mtm.errors import ConcurrentRun
from ai_hedge_fund.mtm.records import (
    CashEventRecord,
    NewCashEvent,
    NewPnlRow,
    PnlRowRecord,
)
from ai_hedge_fund.paper.store import _is_unique_violation

PnlKey = tuple[int, date]
_ISO_FIELDS = ("pnl_date", "as_of_date", "observed_date")
_CASH_ISO = ("event_date", "as_of_date", "observed_date")


class InsertResult(NamedTuple):
    inserted: int
    skipped_existing: int


def _iso(value: object) -> str:
    """ISO text; aware datetimes in UTC so the date prefix never follows the session TZ."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def to_pnl_record(row: PaperPnlDaily) -> PnlRowRecord:
    return PnlRowRecord(
        **{c: getattr(row, c) for c in PnlRowRecord.model_fields if c not in _ISO_FIELDS},
        **{c: _iso(getattr(row, c)) for c in _ISO_FIELDS},
    )


def to_cash_record(row: PaperCashEvent) -> CashEventRecord:
    return CashEventRecord(
        **{c: getattr(row, c) for c in CashEventRecord.model_fields if c not in _CASH_ISO},
        **{c: _iso(getattr(row, c)) for c in _CASH_ISO},
    )


def _existing_keys(db_session: Session, keys: set[PnlKey]) -> set[PnlKey]:
    if not keys:
        return set()
    rows = db_session.execute(
        select(PaperPnlDaily.signal_id, PaperPnlDaily.pnl_date).where(
            tuple_(PaperPnlDaily.signal_id, PaperPnlDaily.pnl_date).in_(list(keys))
        )
    )
    return {(sid, d) for sid, d in rows}


def insert_pnl_rows(db_session: Session, rows: Sequence[NewPnlRow]) -> InsertResult:
    """Insert every row whose ``(signal_id, pnl_date)`` is new, in one transaction.

    Raises:
        ValueError: the batch itself repeats a pair (a caller bug); nothing written.
        ConcurrentRun: a pair appeared between the check and the commit; the whole
            batch was rolled back.
    """
    keys = [(r.signal_id, r.pnl_date) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("batch contains a duplicate (signal_id, pnl_date) pair")
    existing = _existing_keys(db_session, set(keys))
    fresh = [r for r in rows if (r.signal_id, r.pnl_date) not in existing]
    db_session.add_all(
        PaperPnlDaily(**r.model_dump(), as_of_date=normalise_as_of(r.pnl_date)) for r in fresh
    )
    try:
        db_session.commit()
    except IntegrityError as exc:
        db_session.rollback()
        if _is_unique_violation(exc):
            raise ConcurrentRun("a (signal_id, pnl_date) row was written concurrently") from exc
        raise
    return InsertResult(inserted=len(fresh), skipped_existing=len(rows) - len(fresh))


def query_pnl_rows(
    db_session: Session,
    *,
    signal_id: int | None = None,
    on_or_before: date | None = None,
) -> list[PnlRowRecord]:
    """``paper_pnl_daily`` rows ordered by (signal_id, pnl_date)."""
    stmt = select(PaperPnlDaily).order_by(PaperPnlDaily.signal_id, PaperPnlDaily.pnl_date)
    if signal_id is not None:
        stmt = stmt.where(PaperPnlDaily.signal_id == signal_id)
    if on_or_before is not None:
        stmt = stmt.where(PaperPnlDaily.pnl_date <= on_or_before)
    return [to_pnl_record(r) for r in db_session.scalars(stmt)]


def insert_cash_event(db_session: Session, new: NewCashEvent) -> CashEventRecord | None:
    """Append one ``paper_cash_events`` row; None if the activity id is already recorded."""
    row = PaperCashEvent(**new.model_dump(), as_of_date=normalise_as_of(new.event_date))
    db_session.add(row)
    try:
        db_session.commit()
    except IntegrityError as exc:
        db_session.rollback()
        if _is_unique_violation(exc):
            return None
        raise
    db_session.refresh(row)
    return to_cash_record(row)


def query_cash_events(
    db_session: Session, *, ticker: str, on_or_before: date
) -> list[CashEventRecord]:
    """A ticker's cash events with ``event_date <= on_or_before``, oldest first."""
    stmt = (
        select(PaperCashEvent)
        .where(PaperCashEvent.ticker == ticker, PaperCashEvent.event_date <= on_or_before)
        .order_by(PaperCashEvent.event_date, PaperCashEvent.id)
    )
    return [to_cash_record(r) for r in db_session.scalars(stmt)]
