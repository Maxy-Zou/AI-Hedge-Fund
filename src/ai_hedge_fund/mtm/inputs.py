"""Database reads feeding the EOD job (Phase 11, 11-SPEC s6). Read-only.

Every query is bounded by the date being marked: fills by their New York trading
date (``paper_fills.as_of_date``), prices by the exact ``trade_date`` and by
``observed_date <= now``, cash events by ``event_date``. The pure core
re-checks the fill and dividend bounds (11-PREMORTEM #9, #10).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of, trading_date
from ai_hedge_fund.db.models import DailyPrice, EpisodicMemory, PaperFill, PaperTrade
from ai_hedge_fund.mtm.pnl import FillIn


@dataclass(frozen=True)
class SignalPosition:
    signal_id: int
    ticker: str
    side: Literal["buy", "sell"]  # the opening side, for attribution
    fills: tuple[FillIn, ...]
    confidence: int | None
    analysis_payload: dict[str, Any]

    @property
    def first_fill_date(self) -> date:
        return min(trading_date(f.filled_at) for f in self.fills)


@dataclass(frozen=True)
class ClosePrice:
    close_cents: int
    source: str
    row_id: int


def _fills_by_signal(
    db_session: Session, pnl_date: date
) -> dict[int, list[tuple[PaperTrade, PaperFill]]]:
    rows = db_session.execute(
        select(PaperTrade, PaperFill)
        .join(PaperFill, PaperFill.trade_id == PaperTrade.id)
        .where(
            PaperTrade.submit_status == "submitted",
            PaperFill.as_of_date <= normalise_as_of(pnl_date),
        )
        .order_by(PaperTrade.signal_id, PaperFill.filled_at, PaperFill.id)
    ).all()
    grouped: dict[int, list[tuple[PaperTrade, PaperFill]]] = defaultdict(list)
    for trade, fill in rows:
        grouped[trade.signal_id].append((trade, fill))
    return grouped


def _as_fill_in(trade: PaperTrade, fill: PaperFill) -> FillIn:
    return FillIn(
        fill_id=fill.id,
        side=trade.side,  # type: ignore[arg-type]
        qty=fill.filled_qty,
        price_cents=fill.fill_price_cents,
        filled_at=normalise_as_of(fill.filled_at),
    )


def load_positions(db_session: Session, pnl_date: date) -> list[SignalPosition]:
    """Every signal with at least one fill trading on or before ``pnl_date``, by signal id."""
    grouped = _fills_by_signal(db_session, pnl_date)
    positions = []
    for signal_id, pairs in sorted(grouped.items()):
        analysis = db_session.get(EpisodicMemory, signal_id)
        first_trade = pairs[0][0]
        positions.append(
            SignalPosition(
                signal_id=signal_id,
                ticker=first_trade.ticker,
                side=first_trade.side,  # type: ignore[arg-type]
                fills=tuple(_as_fill_in(t, f) for t, f in pairs),
                confidence=analysis.confidence if analysis else None,
                analysis_payload=dict(analysis.payload) if analysis and analysis.payload else {},
            )
        )
    return positions


def load_close(
    db_session: Session, ticker: str, pnl_date: date, now: datetime
) -> ClosePrice | None:
    """That exact day's close -- never an earlier day's (11-PREMORTEM #2).

    Several sources for one day resolve to the most recently observed row, the
    rule ``execution/prices.py`` uses; rows observed after ``now`` are invisible
    (#12).
    """
    row = db_session.execute(
        select(DailyPrice.close_cents, DailyPrice.source, DailyPrice.id)
        .where(
            DailyPrice.ticker == ticker,
            DailyPrice.trade_date == pnl_date,
            DailyPrice.observed_date <= now,
        )
        .order_by(DailyPrice.observed_date.desc(), DailyPrice.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return ClosePrice(close_cents=int(row[0]), source=str(row[1]), row_id=int(row[2]))
