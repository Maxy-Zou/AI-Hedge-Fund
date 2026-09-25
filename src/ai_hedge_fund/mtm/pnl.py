"""Pure mark-to-market core for one signal's position (Phase 11, 11-SPEC s5, A1, D5).

No I/O, no LLM, integer cents throughout. Unrealized P&L marks the open FIFO
lots at the day's *raw* close; realized P&L is FIFO sells plus the dividend
cash credited to this signal (A1 -- cached adj_close cannot measure P&L).

The caller filters inputs to ``pnl_date``; this module re-asserts it and
raises :class:`FutureInputError` rather than trusting the filter, so a
backfill can never see a later fill or dividend (11-PREMORTEM #9, #10).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from ai_hedge_fund.db.dates import trading_date
from ai_hedge_fund.mtm.errors import FutureInputError, OversoldError


@dataclass(frozen=True)
class FillIn:
    fill_id: int
    side: Literal["buy", "sell"]
    qty: int
    price_cents: int
    filled_at: datetime  # aware


@dataclass(frozen=True)
class CashIn:
    """Dividend cash already apportioned to this signal (signed; withholding < 0)."""

    event_id: int
    event_date: date
    amount_cents: int


@dataclass(frozen=True)
class Lot:
    fill_id: int
    qty: int
    price_cents: int


@dataclass(frozen=True)
class PositionMark:
    open_qty: int
    open_cost_cents: int
    realized_pnl_cents: int
    unrealized_pnl_cents: int
    total_pnl_cents: int
    fill_ids: tuple[int, ...]
    cash_event_ids: tuple[int, ...]


def _check_not_future(fills: Sequence[FillIn], dividends: Sequence[CashIn], pnl_date: date) -> None:
    for f in fills:
        if trading_date(f.filled_at) > pnl_date:
            raise FutureInputError(f"fill {f.fill_id} trades after {pnl_date.isoformat()}")
    for d in dividends:
        if d.event_date > pnl_date:
            raise FutureInputError(f"cash event {d.event_id} is after {pnl_date.isoformat()}")


def _sell_fifo(lots: tuple[Lot, ...], fill: FillIn) -> tuple[tuple[Lot, ...], int]:
    """Consume ``fill.qty`` from the oldest lots; return (remaining lots, realized cents)."""
    remaining, realized, kept = fill.qty, 0, list(lots)
    while remaining:
        if not kept:
            raise OversoldError(f"fill {fill.fill_id} sells {fill.qty} but the position is short")
        head = kept[0]
        matched = min(remaining, head.qty)
        realized += matched * (fill.price_cents - head.price_cents)
        remaining -= matched
        kept = (
            kept[1:]
            if matched == head.qty
            else [
                Lot(head.fill_id, head.qty - matched, head.price_cents),
                *kept[1:],
            ]
        )
    return tuple(kept), realized


def _fold_fills(fills: Sequence[FillIn]) -> tuple[tuple[Lot, ...], int]:
    lots: tuple[Lot, ...] = ()
    realized = 0
    for fill in sorted(fills, key=lambda f: (f.filled_at, f.fill_id)):
        if fill.side == "buy":
            lots = (*lots, Lot(fill.fill_id, fill.qty, fill.price_cents))
        else:
            lots, gained = _sell_fifo(lots, fill)
            realized += gained
    return lots, realized


def mark_position(
    fills: Sequence[FillIn],
    dividends: Sequence[CashIn],
    close_cents: int,
    pnl_date: date,
) -> PositionMark:
    """Cumulative P&L of one signal's position at ``pnl_date``'s close.

    Raises:
        ValueError: ``close_cents`` is not positive.
        FutureInputError: an input is dated after ``pnl_date``.
        OversoldError: sells exceed holdings at some point in FIFO order.
    """
    if close_cents <= 0:
        raise ValueError(f"close_cents must be positive, got {close_cents}")
    _check_not_future(fills, dividends, pnl_date)
    lots, realized = _fold_fills(fills)
    open_qty = sum(lot.qty for lot in lots)
    open_cost = sum(lot.qty * lot.price_cents for lot in lots)
    realized += sum(d.amount_cents for d in dividends)
    unrealized = open_qty * close_cents - open_cost
    return PositionMark(
        open_qty=open_qty,
        open_cost_cents=open_cost,
        realized_pnl_cents=realized,
        unrealized_pnl_cents=unrealized,
        total_pnl_cents=realized + unrealized,
        fill_ids=tuple(sorted(f.fill_id for f in fills)),
        cash_event_ids=tuple(sorted(d.event_id for d in dividends)),
    )


def open_quantity_before(fills: Sequence[FillIn], day: date) -> int:
    """Shares held at the start of New York date ``day`` (fills strictly before it).

    Used to weight a dividend across signals. An oversold history holds nothing
    (the job skips that signal anyway).
    """
    earlier = [f for f in fills if trading_date(f.filled_at) < day]
    try:
        lots, _ = _fold_fills(earlier)
    except OversoldError:
        return 0
    return sum(lot.qty for lot in lots)
