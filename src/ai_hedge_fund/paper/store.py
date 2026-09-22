"""Append-only writers for the paper-trading ledger (PT-01..03).

The FK is the mechanical existence check for ``signal_id``; the SELECTs
here exist to raise *typed* errors and to enforce the two invariants a
foreign key cannot express: the episodic row must be an ``analysis`` and
its ticker must match the denormalized one (09-PREMORTEM.md #14, #15).

After any :class:`PaperStoreError` the session has been rolled back and is
immediately usable (#10).
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import EpisodicMemory, PaperFill, PaperTrade
from ai_hedge_fund.paper.errors import (
    DuplicateFill,
    DuplicateSubmission,
    SignalNotFound,
    SignalTickerMismatch,
    SignalWrongRecordType,
    TradeNotFound,
)
from ai_hedge_fund.paper.records import (
    NewPaperFill,
    NewPaperTrade,
    PaperFillRecord,
    PaperTradeRecord,
)


def _iso(value: object) -> str:
    return normalise_as_of(value).isoformat()  # type: ignore[arg-type]


def to_trade_record(row: PaperTrade) -> PaperTradeRecord:
    return PaperTradeRecord(
        id=row.id,
        signal_id=row.signal_id,
        attempt_no=row.attempt_no,
        ticker=row.ticker,
        side=row.side,  # type: ignore[arg-type]
        order_type=row.order_type,  # type: ignore[arg-type]
        quantity=row.quantity,
        limit_price_cents=row.limit_price_cents,
        submit_status=row.submit_status,  # type: ignore[arg-type]
        broker_order_id=row.broker_order_id,
        risk_status_at_submit=row.risk_status_at_submit,
        policy_sha=row.policy_sha,
        review_policy_sha=row.review_policy_sha,
        as_of_date=_iso(row.as_of_date),
        observed_date=_iso(row.observed_date),
        payload=dict(row.payload),
    )


def to_fill_record(row: PaperFill) -> PaperFillRecord:
    return PaperFillRecord(
        id=row.id,
        trade_id=row.trade_id,
        broker_fill_id=row.broker_fill_id,
        filled_qty=row.filled_qty,
        fill_price_cents=row.fill_price_cents,
        filled_at=_iso(row.filled_at),
        as_of_date=_iso(row.as_of_date),
        observed_date=_iso(row.observed_date),
        payload=dict(row.payload),
    )


def _is_unique_violation(exc: IntegrityError) -> bool:
    return "unique" in str(exc.orig).lower()


def insert_paper_trade(db_session: Session, new: NewPaperTrade) -> PaperTradeRecord:
    """Validate lineage, append one ``paper_trades`` row, commit, return the record.

    Raises:
        SignalNotFound: no episodic row with ``new.signal_id``.
        SignalWrongRecordType: the row is not ``record_type='analysis'``.
        SignalTickerMismatch: ``new.ticker`` differs from the row's ticker.
        DuplicateSubmission: ``(signal_id, attempt_no)`` or ``broker_order_id``
            already recorded; the session has been rolled back.
    """
    signal = db_session.get(EpisodicMemory, new.signal_id)
    if signal is None:
        raise SignalNotFound(f"episodic_memory.id={new.signal_id} does not exist")
    if signal.record_type != "analysis":
        raise SignalWrongRecordType(
            f"episodic_memory.id={new.signal_id} is record_type={signal.record_type!r}, "
            "expected 'analysis'"
        )
    if signal.ticker != new.ticker:
        raise SignalTickerMismatch(
            f"signal {new.signal_id} is {signal.ticker!r}, trade says {new.ticker!r}"
        )

    row = PaperTrade(
        **new.model_dump(exclude={"as_of_date"}),
        as_of_date=normalise_as_of(new.as_of_date),
    )
    db_session.add(row)
    try:
        db_session.commit()
    except IntegrityError as exc:
        db_session.rollback()
        if _is_unique_violation(exc):
            raise DuplicateSubmission(
                f"signal_id={new.signal_id} attempt_no={new.attempt_no} "
                f"broker_order_id={new.broker_order_id!r} already recorded"
            ) from exc
        raise
    db_session.refresh(row)  # load server-populated observed_date
    return to_trade_record(row)


def insert_paper_fill(db_session: Session, new: NewPaperFill) -> PaperFillRecord:
    """Append one ``paper_fills`` row for an existing trade, commit, return the record.

    Raises:
        TradeNotFound: no ``paper_trades`` row with ``new.trade_id``.
        DuplicateFill: ``broker_fill_id`` already recorded; session rolled back.
    """
    if db_session.get(PaperTrade, new.trade_id) is None:
        raise TradeNotFound(f"paper_trades.id={new.trade_id} does not exist")

    row = PaperFill(
        **new.model_dump(exclude={"as_of_date", "filled_at"}),
        as_of_date=normalise_as_of(new.as_of_date),
        filled_at=normalise_as_of(new.filled_at),
    )
    db_session.add(row)
    try:
        db_session.commit()
    except IntegrityError as exc:
        db_session.rollback()
        if _is_unique_violation(exc):
            raise DuplicateFill(f"broker_fill_id={new.broker_fill_id!r} already recorded") from exc
        raise
    db_session.refresh(row)
    return to_fill_record(row)
