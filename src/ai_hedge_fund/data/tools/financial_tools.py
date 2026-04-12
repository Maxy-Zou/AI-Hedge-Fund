"""Agent-callable financial summary tool with as_of_date enforcement.

Wraps XbrlClient to provide a simple function interface for agents to
retrieve XBRL financial data with natural language summaries. Enforces
temporal controls and optionally caches results to the XbrlFact model.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings, get_settings
from ai_hedge_fund.data.clients.xbrl_client import MONETARY_CONCEPTS, XbrlClient
from ai_hedge_fund.data.summary import format_financial_summary
from ai_hedge_fund.data.temporal import enforce_as_of_date
from ai_hedge_fund.db.models import XbrlFact

log = structlog.get_logger(__name__)


@enforce_as_of_date
def get_financial_summary(
    ticker: str,
    *,
    as_of_date: date,
    db_session: Session | None = None,
    settings: AppSettings | None = None,
) -> dict[str, Any]:
    """Retrieve XBRL financial summary for a ticker with temporal filtering.

    Uses the @enforce_as_of_date decorator to validate as_of_date. Extracts
    financial metrics via XbrlClient and formats them into a natural language
    summary using format_financial_summary.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL").
        as_of_date: Maximum filed date to include (mandatory, enforced by decorator).
        db_session: Optional SQLAlchemy session for caching results.
        settings: Optional AppSettings (defaults to get_settings()).

    Returns:
        Dict with keys: ticker, fiscal_period, fiscal_year, metrics, summary_text.

    Raises:
        ValueError: If as_of_date is None (via decorator) or edgar_identity not configured.
    """
    resolved_settings = settings or get_settings()

    if not resolved_settings.edgar_identity:
        msg = "edgar_identity is not configured -- set EDGAR_IDENTITY in environment or .env"
        raise ValueError(msg)

    log.info(
        "financial_tools.get_financial_summary",
        ticker=ticker,
        as_of_date=as_of_date.isoformat(),
    )

    client = XbrlClient(resolved_settings.edgar_identity)
    result = client.get_financial_metrics(ticker, as_of_date)

    metrics = result["metrics"]

    # Build NL summary using format_financial_summary
    summary_text = _build_summary_text(
        ticker=ticker,
        fiscal_year=result["fiscal_year"],
        fiscal_period=result["fiscal_period"],
        metrics=metrics,
    )

    output = {
        "ticker": ticker,
        "fiscal_period": result["fiscal_period"],
        "fiscal_year": result["fiscal_year"],
        "metrics": metrics,
        "summary_text": summary_text,
    }

    # Cache to database if session provided
    if db_session is not None:
        _cache_xbrl_facts(
            db_session=db_session,
            ticker=ticker,
            fiscal_year=result["fiscal_year"],
            fiscal_period=result["fiscal_period"],
            metrics=metrics,
        )

    return output


def _build_summary_text(
    *,
    ticker: str,
    fiscal_year: int,
    fiscal_period: str,
    metrics: dict[str, dict[str, int | float | None]],
) -> str:
    """Build a natural language summary from financial metrics.

    Extracts the fields required by format_financial_summary from the
    metrics dict. Computes operating margin from operating income and revenue.

    Args:
        ticker: Stock ticker symbol.
        fiscal_year: Fiscal year of the current data.
        fiscal_period: Fiscal period label (e.g., "FY").
        metrics: Dict mapping concept to {current, prior} values.

    Returns:
        Natural language summary string.
    """
    rev = metrics.get("revenue", {})
    ni = metrics.get("net_income", {})
    oi = metrics.get("operating_income", {})
    eps = metrics.get("eps_diluted", {})

    rev_current = rev.get("current", 0) or 0
    rev_prior = rev.get("prior", 0) or 0
    ni_current = ni.get("current", 0) or 0
    ni_prior = ni.get("prior", 0) or 0
    oi_current = oi.get("current", 0) or 0
    oi_prior = oi.get("prior", 0) or 0
    eps_current = eps.get("current", 0.0) or 0.0
    eps_prior = eps.get("prior", 0.0) or 0.0

    # Compute operating margin (operating income / revenue)
    op_margin_current = oi_current / rev_current if rev_current != 0 else 0.0
    op_margin_prior = oi_prior / rev_prior if rev_prior != 0 else 0.0

    period_label = f"{fiscal_period}{fiscal_year}" if fiscal_period else f"FY{fiscal_year}"

    return format_financial_summary(
        ticker=ticker,
        revenue_current_cents=rev_current,
        revenue_prior_cents=rev_prior,
        net_income_current_cents=ni_current,
        net_income_prior_cents=ni_prior,
        operating_margin_current=op_margin_current,
        operating_margin_prior=op_margin_prior,
        fiscal_period=period_label,
        eps_current=eps_current,
        eps_prior=eps_prior,
    )


def _cache_xbrl_facts(
    *,
    db_session: Session,
    ticker: str,
    fiscal_year: int,
    fiscal_period: str,
    metrics: dict[str, dict[str, int | float | None]],
) -> None:
    """Cache XBRL facts to XbrlFact model.

    Args:
        db_session: SQLAlchemy session.
        ticker: Stock ticker symbol.
        fiscal_year: Fiscal year.
        fiscal_period: Fiscal period.
        metrics: Dict mapping concept to {current, prior} values.
    """
    now = datetime.now(UTC)

    for concept, values in metrics.items():
        current_val = values.get("current")
        if current_val is None:
            continue

        # Check if already cached
        existing = (
            db_session.query(XbrlFact)
            .filter_by(
                ticker=ticker,
                concept=concept,
                fiscal_period=fiscal_period,
                fiscal_year=fiscal_year,
            )
            .first()
        )
        if existing is not None:
            continue

        # Determine value_cents: monetary concepts already in cents from XbrlClient
        # Non-monetary concepts (eps, shares) store raw value as int
        if concept in MONETARY_CONCEPTS:
            value_cents = int(current_val)
        elif isinstance(current_val, float):
            # Non-monetary floats (e.g., EPS): store scaled by 100
            value_cents = int(current_val * 100)
        else:
            value_cents = int(current_val)

        unit = "USD" if concept in MONETARY_CONCEPTS else "shares"

        record = XbrlFact(
            ticker=ticker,
            cik="",  # CIK not available from metrics; populated on full pipeline
            concept=concept,
            value_cents=value_cents,
            unit=unit,
            fiscal_period=fiscal_period,
            fiscal_year=fiscal_year,
            filed_date=now,
            as_of_date=now,
            observed_date=now,
        )
        db_session.add(record)

    db_session.flush()
    log.info("financial_tools.cached", ticker=ticker, count=len(metrics))
