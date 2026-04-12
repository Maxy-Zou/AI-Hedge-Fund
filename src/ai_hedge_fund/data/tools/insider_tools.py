"""Agent-callable insider trade cluster detection tool.

Provides get_insider_clusters() which fetches Form 4 insider trades,
detects purchase clusters, and returns natural language summaries
for LLM consumption. Enforces as_of_date and filters by filing_date
to prevent look-ahead bias.

Threat mitigations:
- T-02-12: Filters on filing_date (not trade_date) for temporal correctness
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings, get_settings
from ai_hedge_fund.data.clients.form4_client import (
    Form4Client,
    InsiderCluster,
    detect_purchase_clusters,
)
from ai_hedge_fund.data.summary import format_insider_summary
from ai_hedge_fund.data.temporal import enforce_as_of_date
from ai_hedge_fund.db.models import InsiderTrade


def _cluster_to_dict(cluster: InsiderCluster) -> dict[str, Any]:
    """Convert an InsiderCluster to a dict for summary formatting.

    Args:
        cluster: InsiderCluster dataclass instance.

    Returns:
        Dict compatible with format_insider_summary.
    """
    return {
        "insiders": list(cluster.insiders),
        "total_shares": cluster.total_shares,
        "total_value_cents": cluster.total_value_cents,
        "start_date": cluster.start_date.isoformat(),
        "end_date": cluster.end_date.isoformat(),
        "cluster_size": cluster.cluster_size,
    }


def _store_trades(db_session: Session, ticker: str, trades: list[dict[str, Any]]) -> None:
    """Cache insider trades to InsiderTrade table.

    Uses a check-before-insert pattern to emulate ON CONFLICT DO NOTHING
    for SQLite compatibility in tests.

    Args:
        db_session: SQLAlchemy session.
        ticker: Stock ticker symbol.
        trades: List of trade dicts.
    """
    for t in trades:
        # Check for existing row to emulate ON CONFLICT DO NOTHING
        existing = (
            db_session.query(InsiderTrade)
            .filter(
                InsiderTrade.ticker == ticker,
                InsiderTrade.insider_name == t["insider_name"],
                InsiderTrade.trade_date == t["trade_date"],
                InsiderTrade.trade_type == t["trade_type"],
                InsiderTrade.shares == t["shares"],
            )
            .first()
        )
        if existing is not None:
            continue

        td = t["trade_date"]
        fd = t["filing_date"]

        row = InsiderTrade(
            ticker=ticker,
            insider_name=t["insider_name"],
            insider_title=t.get("insider_title"),
            trade_type=t["trade_type"],
            shares=t["shares"],
            price_cents=t.get("price_cents"),
            value_cents=t.get("value_cents"),
            trade_date=t["trade_date"],
            filing_date=datetime(fd.year, fd.month, fd.day, tzinfo=UTC)
            if isinstance(fd, date) and not isinstance(fd, datetime)
            else fd,
            as_of_date=datetime(td.year, td.month, td.day, tzinfo=UTC)
            if isinstance(td, date) and not isinstance(td, datetime)
            else td,
        )
        db_session.add(row)

    db_session.commit()


@enforce_as_of_date
def get_insider_clusters(
    ticker: str,
    *,
    as_of_date: date,
    lookback_days: int = 90,
    window_days: int = 14,
    min_insiders: int = 3,
    db_session: Session | None = None,
    settings: AppSettings | None = None,
) -> dict[str, Any]:
    """Get insider purchase clusters with filing_date filtering.

    Fetches insider trades from Form 4 filings, filters by filing_date
    to prevent look-ahead bias, detects purchase clusters, and returns
    a natural language summary for LLM consumption.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL").
        as_of_date: Temporal cutoff date (enforced by decorator).
        lookback_days: How far back to look for trades (default 90 days).
        window_days: Cluster window in days (default 14).
        min_insiders: Minimum insiders for a cluster (default 3).
        db_session: Optional SQLAlchemy session for cache writes.
        settings: Optional AppSettings for EDGAR identity.

    Returns:
        Dict with keys: ticker, clusters (list of dicts), summary_text.
    """
    if settings is None:
        settings = get_settings()

    # Fetch trades from Form 4 filings
    client = Form4Client(edgar_identity=settings.edgar_identity)
    all_trades = client.get_insider_trades(ticker)

    # Filter by filing_date <= as_of_date (temporal correctness, T-02-12)
    cutoff_start = as_of_date - timedelta(days=lookback_days)
    filtered_trades = [
        t
        for t in all_trades
        if t.get("filing_date") is not None
        and t["filing_date"] <= as_of_date
        and t["trade_date"] >= cutoff_start
    ]

    # Detect clusters from purchase trades only
    purchase_trades = [t for t in filtered_trades if t["trade_type"] == "purchase"]
    clusters = detect_purchase_clusters(
        purchase_trades,
        window_days=window_days,
        min_insiders=min_insiders,
        ticker=ticker,
    )

    # Cache trades if session provided
    if db_session is not None and filtered_trades:
        _store_trades(db_session, ticker, filtered_trades)

    # Convert clusters to dicts for summary formatting
    cluster_dicts = [_cluster_to_dict(c) for c in clusters]

    # Generate NL summary
    summary_text = format_insider_summary(
        ticker=ticker,
        clusters=cluster_dicts,
        as_of_date=as_of_date,
    )

    return {
        "ticker": ticker,
        "clusters": cluster_dicts,
        "summary_text": summary_text,
    }
