"""Agent-callable macro context tool with as_of_date enforcement.

Provides macroeconomic environment context (interest rates, inflation,
GDP, yield curve) to complement ticker-specific data. These signals
inform investment thesis quality and conviction.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings, get_settings
from ai_hedge_fund.data.clients.fred_client import FRED_SERIES, FredClient
from ai_hedge_fund.data.summary import format_macro_summary
from ai_hedge_fund.data.temporal import enforce_as_of_date
from ai_hedge_fund.db.models import MacroIndicator

logger = structlog.get_logger(__name__)


@enforce_as_of_date
def get_macro_context(
    *,
    as_of_date: date,
    db_session: Session | None = None,
    settings: AppSettings | None = None,
) -> dict[str, Any]:
    """Retrieve macroeconomic context as of a given date.

    Fetches latest values for all FRED series, computes CPI YoY and
    GDP growth, and produces a natural language summary for agent
    consumption. No ticker parameter -- macro data is market-wide.

    Args:
        as_of_date: Temporal cutoff date. Observations after this date
            are excluded.
        db_session: Optional SQLAlchemy session for caching observations.
        settings: Optional AppSettings instance. Created from env if not provided.

    Returns:
        Dict with keys: indicators, cpi_yoy_pct, gdp_growth_pct, summary_text.

    Raises:
        ValueError: If as_of_date is None or fred_api_key is not configured.
    """
    resolved_settings = settings if settings is not None else get_settings()

    if not resolved_settings.fred_api_key:
        msg = "fred_api_key is required -- set FRED_API_KEY in .env"
        raise ValueError(msg)

    client = FredClient(api_key=resolved_settings.fred_api_key)

    # Get latest values for all FRED series
    indicators = client.get_latest_values(as_of_date=as_of_date)

    # Compute derived indicators
    cpi_yoy_pct = client.compute_cpi_yoy(as_of_date=as_of_date)
    gdp_growth_pct = client.compute_gdp_growth(as_of_date=as_of_date)

    # Cache to database if session provided
    if db_session is not None:
        _cache_indicators(indicators, as_of_date, db_session)

    # Generate natural language summary
    summary_text = _build_summary(
        indicators=indicators,
        cpi_yoy_pct=cpi_yoy_pct,
        gdp_growth_pct=gdp_growth_pct,
        as_of_date=as_of_date,
    )

    return {
        "indicators": indicators,
        "cpi_yoy_pct": cpi_yoy_pct,
        "gdp_growth_pct": gdp_growth_pct,
        "summary_text": summary_text,
    }


def _build_summary(
    *,
    indicators: dict[str, float | None],
    cpi_yoy_pct: float | None,
    gdp_growth_pct: float | None,
    as_of_date: date,
) -> str:
    """Build a natural language macro summary.

    Uses format_macro_summary when all required values are available,
    falls back to a partial summary when some indicators are missing.

    Args:
        indicators: Dict of {series_name: value}.
        cpi_yoy_pct: Computed CPI YoY percentage.
        gdp_growth_pct: Computed GDP growth percentage.
        as_of_date: Date of the data.

    Returns:
        Natural language summary string.
    """
    fed_funds = indicators.get("fed_funds_rate")
    yield_spread = indicators.get("yield_curve_spread")
    treasury_10y = indicators.get("treasury_10y")

    # Use 0.0 defaults for missing values so formatter can still produce output
    return format_macro_summary(
        fed_funds_rate=fed_funds if fed_funds is not None else 0.0,
        cpi_yoy_pct=cpi_yoy_pct if cpi_yoy_pct is not None else 0.0,
        gdp_growth_pct=gdp_growth_pct if gdp_growth_pct is not None else 0.0,
        yield_spread=yield_spread if yield_spread is not None else 0.0,
        treasury_10y=treasury_10y if treasury_10y is not None else 0.0,
        as_of_date=as_of_date,
    )


def _cache_indicators(
    indicators: dict[str, float | None],
    as_of_date: date,
    db_session: Session,
) -> None:
    """Cache indicator observations to MacroIndicator model.

    Uses INSERT ON CONFLICT DO NOTHING pattern (check-before-insert)
    to prevent duplicate observations.

    Args:
        indicators: Dict of {series_name: value}.
        as_of_date: The observation date.
        db_session: Active SQLAlchemy session.
    """
    for name, value in indicators.items():
        if value is None:
            continue

        config = FRED_SERIES.get(name)
        if config is None:
            continue

        series_id = config["series_id"]

        # Check if observation already exists
        existing = (
            db_session.query(MacroIndicator)
            .filter_by(series_id=series_id, observation_date=as_of_date)
            .first()
        )
        if existing is not None:
            continue

        record = MacroIndicator(
            series_id=series_id,
            series_name=config["description"],
            value=value,
            observation_date=as_of_date,
            as_of_date=as_of_date,
            observed_date=date.today(),
        )
        db_session.add(record)

    db_session.flush()
