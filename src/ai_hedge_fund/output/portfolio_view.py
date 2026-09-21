"""Portfolio view query (Phase 8 SIG-02).

Read-only query over append-only ``episodic_memory``. Returns a sector-keyed
dict of latest-per-ticker analysis rows ranked by conviction DESC, then
``as_of_date`` DESC. No caching -- the append-only table IS the cache; each
call reflects current truth (Pitfall C).

Temporal filter: ``as_of_date <= target`` (SIG-02 never leaks future data --
Phase-7 Pitfall 2 carried forward).

The result shape is::

    {
        "Technology": [
            {"ticker": "AAPL", "sector": "Technology", "conviction": 85,
             "direction": "long", "thesis_summary": "...",
             "as_of_date": "2026-04-20", "episodic_id": 7,
             "policy_sha": "a"*64},
            {"ticker": "MSFT", ...},
        ],
        "Healthcare": [...],
    }

Threat mitigations:
    T-08-15 (caching stale data): NO memoization decorator / module-level
            memo dict. Each call issues a fresh SQLAlchemy query; append-only
            truth means the DB IS the cache.
    T-08-17 (spoofing: review/outcome rows surfaced as analyses): query filters
            ``record_type == 'analysis'`` explicitly.
    T-08-18 (future-date leak): ``as_of_date <= target`` filter.
    T-08-20 (unbounded rows / DoS): ``limit_per_sector`` default 50.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.memory.episodic import _normalise_as_of


def query_portfolio_view(
    db_session: Session,
    *,
    as_of_date: str | date | datetime,
    sector: str | None = None,
    limit_per_sector: int = 50,
) -> dict[str, list[dict[str, Any]]]:
    """Return a ranked portfolio view as ``{sector: [entry, ...]}``.

    For each ticker, selects the LATEST ``record_type='analysis'`` row visible
    as of ``as_of_date``. Review and outcome rows are excluded. Within each
    sector, entries are ranked by ``conviction`` DESC then ``as_of_date`` DESC.
    Bounded by ``limit_per_sector`` (DoS guard).

    Args:
        db_session: Open SQLAlchemy session.
        as_of_date: Temporal cutoff; rows dated after this are not returned.
        sector: Optional sector filter. If ``None``, all sectors are returned.
        limit_per_sector: Max tickers returned per sector (default 50).

    Returns:
        Sector-keyed dict; each value is a list of entries with keys
        ``ticker``, ``sector``, ``conviction``, ``direction``,
        ``thesis_summary``, ``as_of_date`` (ISO string), ``episodic_id``,
        ``policy_sha``.

    Freshness invariant (SIG-02): no in-process cache. Each call queries the
    DB; because ``episodic_memory`` is append-only, a new analysis row written
    between two calls WILL appear on the second call without any explicit
    refresh (Pitfall C mitigation).
    """
    target = _normalise_as_of(as_of_date)

    q = (
        select(EpisodicMemory)
        .where(EpisodicMemory.record_type == "analysis")
        .where(EpisodicMemory.as_of_date <= target)
        .order_by(EpisodicMemory.ticker, EpisodicMemory.as_of_date.desc())
    )
    if sector is not None:
        q = q.where(EpisodicMemory.sector == sector)

    rows = db_session.scalars(q).all()

    # Pick latest row per ticker (query already sorted DESC by as_of_date
    # within each ticker, so the first row seen per ticker is the latest).
    latest_by_ticker: dict[str, EpisodicMemory] = {}
    for row in rows:
        if row.ticker not in latest_by_ticker:
            latest_by_ticker[row.ticker] = row

    # Group by sector, then rank within each sector
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in latest_by_ticker.values():
        payload = row.payload or {}
        thesis_data = payload.get("thesis") or {}
        thesis_summary = thesis_data.get("bull_case") or thesis_data.get("summary") or ""
        entry = {
            "ticker": row.ticker,
            "sector": row.sector,
            "conviction": row.confidence if row.confidence is not None else 0,
            "direction": row.signal_direction,
            "thesis_summary": thesis_summary,
            # Always render as date-only (YYYY-MM-DD). The column is ``Date``
            # but some dialects (and some historical rows written via
            # ``_normalise_as_of``) surface as ``datetime``; slicing to the
            # first 10 chars normalises both forms to the stable ISO date.
            "as_of_date": (
                row.as_of_date.isoformat()[:10]
                if hasattr(row.as_of_date, "isoformat")
                else str(row.as_of_date)[:10]
            ),
            "episodic_id": row.id,
            "policy_sha": row.policy_sha,
        }
        grouped[row.sector].append(entry)

    # Rank within each sector (conviction DESC, as_of_date DESC) and truncate.
    for s, entries in list(grouped.items()):
        entries.sort(
            key=lambda e: (e["conviction"], e["as_of_date"]),
            reverse=True,
        )
        grouped[s] = entries[:limit_per_sector]

    return dict(grouped)
