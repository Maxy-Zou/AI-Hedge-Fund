"""End-of-day mark-to-market job (Phase 11, MTM-01/02/04; 11-SPEC s6, D6, A1).

Pure Python, no LLM. For one completed trading day it marks every signal with
fills at that day's close, credits apportioned dividends, attaches the signal's
frozen attribution labels, and skip-or-inserts one cumulative row per
``(signal, date)`` -- never an UPDATE (criterion 11.2). A signal is skipped,
never guessed, when its exact-date price is missing, when a corporate action
happened after its first fill (not applied this phase), or when its fills oversell.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import structlog
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import MARKET_TZ, trading_date
from ai_hedge_fund.mtm.attribution import attribution_for
from ai_hedge_fund.mtm.dividends import apportion
from ai_hedge_fund.mtm.errors import IncompleteTradingDay, OversoldError
from ai_hedge_fund.mtm.inputs import ClosePrice, SignalPosition, load_close, load_positions
from ai_hedge_fund.mtm.pnl import CashIn, mark_position, open_quantity_before
from ai_hedge_fund.mtm.policy import MtmPolicy, compute_mtm_policy_sha
from ai_hedge_fund.mtm.records import NON_CASH_ACTIVITY_TYPES, CashEventRecord, NewPnlRow
from ai_hedge_fund.mtm.store import insert_pnl_rows, query_cash_events

logger = structlog.get_logger(__name__)

_MARKET_CLOSE = time(16, 0)


@dataclass(frozen=True)
class JobResult:
    pnl_date: date
    inserted: int
    skipped_existing: int
    skipped_no_price: tuple[int, ...]
    skipped_corporate_action: tuple[int, ...]
    skipped_oversold: tuple[int, ...]
    rows: tuple[NewPnlRow, ...]  # every row computed (what --dry-run prints)


def complete_at(pnl_date: date, policy: MtmPolicy) -> datetime:
    """16:00 New York on ``pnl_date`` plus the policy buffer, as an aware datetime."""
    return datetime.combine(pnl_date, _MARKET_CLOSE, tzinfo=MARKET_TZ) + timedelta(
        minutes=policy.market_close_buffer_minutes
    )


def check_completed_day(pnl_date: date, now: datetime, policy: MtmPolicy) -> None:
    """D6: only a weekday whose close (+ buffer) has passed may be marked (11-PREMORTEM #1)."""
    if pnl_date.weekday() >= 5:
        raise IncompleteTradingDay(f"{pnl_date.isoformat()} is not a weekday")
    today = trading_date(now)
    closes_at = complete_at(pnl_date, policy)
    if pnl_date > today or now < closes_at:
        raise IncompleteTradingDay(
            f"{pnl_date.isoformat()} has not closed yet (complete at {closes_at.isoformat()})"
        )


def last_completed_trading_day(now: datetime, policy: MtmPolicy) -> date:
    """The most recent weekday whose close (+ buffer) is at or before ``now``."""
    day = trading_date(now)
    for _ in range(7):
        try:
            check_completed_day(day, now, policy)
            return day
        except IncompleteTradingDay:
            day -= timedelta(days=1)
    raise AssertionError("unreachable: a week always contains a completed weekday")


def _dividend_credits(
    positions: Sequence[SignalPosition], events: Sequence[CashEventRecord]
) -> dict[int, list[CashIn]]:
    """Each dividend split pro rata by shares held at the start of its date (11-PREMORTEM #15)."""
    credits: dict[int, list[CashIn]] = defaultdict(list)
    for ev in events:
        day = date.fromisoformat(ev.event_date)
        weights = {p.signal_id: open_quantity_before(p.fills, day) for p in positions}
        shares = apportion(ev.net_amount_cents, weights)
        if not shares:
            logger.warning("dividend_unallocated", event_id=ev.id, ticker=ev.ticker, day=str(day))
        for signal_id, cents in shares.items():
            credits[signal_id].append(CashIn(event_id=ev.id, event_date=day, amount_cents=cents))
    return credits


def _row(
    pos: SignalPosition,
    price: ClosePrice,
    credits: list[CashIn],
    pnl_date: date,
    policy: MtmPolicy,
    policy_sha: str,
) -> NewPnlRow:
    mark = mark_position(pos.fills, credits, price.close_cents, pnl_date)
    attribution = attribution_for(pos.analysis_payload, pos.confidence, pos.side, policy)
    return NewPnlRow(
        signal_id=pos.signal_id,
        pnl_date=pnl_date,
        ticker=pos.ticker,
        open_qty=mark.open_qty,
        open_cost_cents=mark.open_cost_cents,
        mark_close_cents=price.close_cents,
        price_source=price.source,
        realized_pnl_cents=mark.realized_pnl_cents,
        unrealized_pnl_cents=mark.unrealized_pnl_cents,
        total_pnl_cents=mark.total_pnl_cents,
        attribution=attribution.model_dump(mode="json"),
        mtm_policy_sha=policy_sha,
        payload={
            "fill_ids": list(mark.fill_ids),
            "cash_event_ids": list(mark.cash_event_ids),
            "price_row_id": price.row_id,
        },
    )


@dataclass
class _Tally:
    rows: list[NewPnlRow]
    no_price: list[int]
    corporate: list[int]
    oversold: list[int]


def _price_postdates_later_action(
    db_session: Session, ticker: str, pnl_date: date, price: ClosePrice
) -> bool:
    """Review H4: vendors split-adjust history as of the download day, so a close for
    ``pnl_date`` fetched after a later split is in post-split units -- unusable here."""
    fetched_on = trading_date(price.observed_date)
    events = query_cash_events(db_session, ticker=ticker, on_or_before=fetched_on)
    return any(
        e.activity_type in NON_CASH_ACTIVITY_TYPES and date.fromisoformat(e.event_date) > pnl_date
        for e in events
    )


def _mark_ticker(
    db_session: Session,
    positions: list[SignalPosition],
    pnl_date: date,
    now: datetime,
    policy: MtmPolicy,
    policy_sha: str,
    tally: _Tally,
) -> None:
    ticker = positions[0].ticker
    not_before = complete_at(pnl_date, policy).astimezone(UTC)  # UTC: SQLite compares text
    price = load_close(db_session, ticker, pnl_date, not_before=not_before, now=now)
    if price is None:
        tally.no_price.extend(p.signal_id for p in positions)
        return
    if _price_postdates_later_action(db_session, ticker, pnl_date, price):
        tally.corporate.extend(p.signal_id for p in positions)
        return
    events = query_cash_events(db_session, ticker=ticker, on_or_before=pnl_date)
    actions = [
        date.fromisoformat(e.event_date)
        for e in events
        if e.activity_type in NON_CASH_ACTIVITY_TYPES
    ]
    credits = _dividend_credits(
        positions, [e for e in events if e.activity_type not in NON_CASH_ACTIVITY_TYPES]
    )
    for pos in positions:
        if any(day > pos.first_fill_date for day in actions):
            tally.corporate.append(pos.signal_id)
            continue
        try:
            tally.rows.append(
                _row(pos, price, credits[pos.signal_id], pnl_date, policy, policy_sha)
            )
        except OversoldError as exc:
            logger.error("mtm_oversold", signal_id=pos.signal_id, detail=str(exc))
            tally.oversold.append(pos.signal_id)


def run_mark_to_market(
    db_session: Session,
    pnl_date: date,
    policy: MtmPolicy,
    *,
    now: datetime,
    dry_run: bool = False,
) -> JobResult:
    """Mark every held signal at ``pnl_date``'s close and append the new rows.

    Raises:
        IncompleteTradingDay: the day is a weekend or has not closed (nothing written).
        ConcurrentRun: another run wrote a colliding row; this batch was rolled back.
    """
    check_completed_day(pnl_date, now, policy)
    policy_sha = compute_mtm_policy_sha(policy)
    by_ticker: dict[str, list[SignalPosition]] = defaultdict(list)
    for pos in load_positions(db_session, pnl_date):
        by_ticker[pos.ticker].append(pos)
    tally = _Tally([], [], [], [])
    for ticker in sorted(by_ticker):
        _mark_ticker(db_session, by_ticker[ticker], pnl_date, now, policy, policy_sha, tally)
    inserted = skipped = 0
    if not dry_run:
        inserted, skipped = insert_pnl_rows(db_session, tally.rows)
    result = JobResult(
        pnl_date=pnl_date,
        inserted=inserted,
        skipped_existing=skipped,
        skipped_no_price=tuple(sorted(tally.no_price)),
        skipped_corporate_action=tuple(sorted(tally.corporate)),
        skipped_oversold=tuple(sorted(tally.oversold)),
        rows=tuple(tally.rows),
    )
    logger.info(
        "mark_to_market_complete",
        pnl_date=pnl_date.isoformat(),
        dry_run=dry_run,
        inserted=inserted,
        skipped_existing=skipped,
        skipped_no_price=len(result.skipped_no_price),
        skipped_corporate_action=len(result.skipped_corporate_action),
        skipped_oversold=len(result.skipped_oversold),
    )
    return result
