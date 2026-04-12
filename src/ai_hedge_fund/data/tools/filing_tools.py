"""Agent-callable filing retrieval tool with as_of_date enforcement.

Wraps EdgarClient to provide a simple function interface for agents to
retrieve SEC filing sections. Enforces temporal controls and optionally
caches results to the SecFiling model.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings, get_settings
from ai_hedge_fund.data.clients.edgar_client import EdgarClient
from ai_hedge_fund.data.temporal import enforce_as_of_date
from ai_hedge_fund.db.models import SecFiling

log = structlog.get_logger(__name__)


@enforce_as_of_date
def get_filing_sections(
    ticker: str,
    *,
    as_of_date: date,
    form_type: str = "10-K",
    max_filings: int = 5,
    db_session: Session | None = None,
    settings: AppSettings | None = None,
) -> list[dict[str, Any]]:
    """Retrieve SEC filing sections for a ticker with temporal filtering.

    Uses the @enforce_as_of_date decorator to validate that as_of_date is
    provided and not in the future. Filters filings by filing_date to
    prevent look-ahead bias.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL").
        as_of_date: Maximum filing date to include (mandatory, enforced by decorator).
        form_type: SEC form type ("10-K" or "10-Q").
        max_filings: Maximum number of filings to return.
        db_session: Optional SQLAlchemy session for caching results.
        settings: Optional AppSettings (defaults to get_settings()).

    Returns:
        List of dicts with keys: accession_no, filing_date, form_type,
        sections (dict of section_name -> text).

    Raises:
        ValueError: If as_of_date is None (via decorator) or edgar_identity not configured.
    """
    resolved_settings = settings or get_settings()

    if not resolved_settings.edgar_identity:
        msg = "edgar_identity is not configured -- set EDGAR_IDENTITY in environment or .env"
        raise ValueError(msg)

    log.info(
        "filing_tools.get_filing_sections",
        ticker=ticker,
        as_of_date=as_of_date.isoformat(),
        form_type=form_type,
    )

    client = EdgarClient(resolved_settings.edgar_identity)
    results = client.get_filing_sections(
        ticker=ticker,
        form_type=form_type,
        filing_date_cutoff=as_of_date,
        max_filings=max_filings,
    )

    # Cache to database if session provided
    if db_session is not None:
        _cache_filing_results(
            db_session=db_session,
            ticker=ticker,
            results=results,
        )

    return results


def _cache_filing_results(
    *,
    db_session: Session,
    ticker: str,
    results: list[dict[str, Any]],
) -> None:
    """Cache filing results to SecFiling model.

    Uses INSERT ON CONFLICT DO NOTHING semantics by checking for
    existing records before inserting.

    Args:
        db_session: SQLAlchemy session.
        ticker: Stock ticker symbol.
        results: Filing results from EdgarClient.
    """
    now = datetime.now(UTC)

    for result in results:
        # Check if already cached
        existing = (
            db_session.query(SecFiling)
            .filter_by(ticker=ticker, accession_no=result["accession_no"])
            .first()
        )
        if existing is not None:
            continue

        filing_date = result["filing_date"]
        if isinstance(filing_date, date) and not isinstance(filing_date, datetime):
            filing_date = datetime(filing_date.year, filing_date.month, filing_date.day, tzinfo=UTC)

        record = SecFiling(
            ticker=ticker,
            accession_no=result["accession_no"],
            form_type=result["form_type"],
            filing_date=filing_date,
            sections_json=json.dumps(result["sections"]),
            as_of_date=now,
            observed_date=now,
        )
        db_session.add(record)

    db_session.flush()
    log.info("filing_tools.cached", ticker=ticker, count=len(results))
