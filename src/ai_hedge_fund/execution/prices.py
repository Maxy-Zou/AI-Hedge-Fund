"""As-of price lookup for deterministic sizing (Phase 10, D5).

Reads the latest cached adjusted close on or before the analysis date from
``daily_prices`` -- never a live quote -- so a trade's size is reproducible
from the row alone. ``trade_date <= as_of`` (inclusive) keeps a signal from
being sized with future prices (09-PREMORTEM #4).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import DailyPrice
from ai_hedge_fund.execution.errors import NoPriceAvailable


def latest_adj_close_cents(
    db_session: Session, ticker: str, as_of_date: str | date | datetime
) -> int:
    """Return the most recent ``adj_close_cents`` with ``trade_date <= as_of_date``.

    Raises:
        NoPriceAvailable: no cached row for the ticker on or before that date.
    """
    cutoff = normalise_as_of(as_of_date).date()
    row = db_session.execute(
        select(DailyPrice.adj_close_cents)
        .where(DailyPrice.ticker == ticker)
        .where(DailyPrice.trade_date <= cutoff)
        .order_by(DailyPrice.trade_date.desc())
        .limit(1)
    ).first()
    if row is None:
        raise NoPriceAvailable(f"no cached price for {ticker} on or before {cutoff.isoformat()}")
    return int(row[0])
