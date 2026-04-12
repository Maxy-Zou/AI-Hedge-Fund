"""Agent-callable price history tool with cache-first pattern.

Provides get_price_history() which checks the DailyPrice cache table
before calling external APIs. Enforces as_of_date to prevent look-ahead
bias. Returns a dict with raw prices, computed stats, and a natural
language summary for LLM consumption.

Threat mitigations:
- T-02-09: Logged source field enables cross-validation when both sources available
- T-02-10: Cache-first avoids repeated external calls
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings, get_settings
from ai_hedge_fund.data.clients.price_client import PriceClient
from ai_hedge_fund.data.summary import format_price_summary
from ai_hedge_fund.data.temporal import enforce_as_of_date
from ai_hedge_fund.db.models import DailyPrice


def _compute_stats(prices: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics from a list of price dicts.

    Uses adj_close_cents for return and volatility calculations per
    CLAUDE.md convention (always use adjusted close for returns).

    Args:
        prices: List of price dicts sorted by trade_date ascending.

    Returns:
        Dict with return_pct, volatility_pct, high_52w_cents, low_52w_cents.
    """
    if not prices:
        return {
            "return_pct": 0.0,
            "volatility_pct": 0.0,
            "high_52w_cents": 0,
            "low_52w_cents": 0,
        }

    adj_closes = [p["adj_close_cents"] for p in prices]
    first = adj_closes[0]
    last = adj_closes[-1]

    # Period return
    return_pct = ((last - first) / first) * 100 if first != 0 else 0.0

    # Daily log returns for volatility
    if len(adj_closes) >= 2:
        log_returns = []
        for i in range(1, len(adj_closes)):
            if adj_closes[i - 1] > 0 and adj_closes[i] > 0:
                log_returns.append(math.log(adj_closes[i] / adj_closes[i - 1]))

        if log_returns:
            mean_ret = sum(log_returns) / len(log_returns)
            variance = sum((r - mean_ret) ** 2 for r in log_returns) / len(log_returns)
            daily_vol = math.sqrt(variance)
            annualized_vol = daily_vol * math.sqrt(252) * 100
        else:
            annualized_vol = 0.0
    else:
        annualized_vol = 0.0

    high_52w = max(adj_closes)
    low_52w = min(adj_closes)

    return {
        "return_pct": round(return_pct, 2),
        "volatility_pct": round(annualized_vol, 2),
        "high_52w_cents": high_52w,
        "low_52w_cents": low_52w,
    }


def _query_cached_prices(
    db_session: Session,
    ticker: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Query DailyPrice table for cached price data.

    Args:
        db_session: SQLAlchemy session.
        ticker: Stock ticker symbol.
        start_date: Start of date range (inclusive).
        end_date: End of date range (inclusive).

    Returns:
        List of price dicts from the cache.
    """
    rows = (
        db_session.query(DailyPrice)
        .filter(
            DailyPrice.ticker == ticker,
            DailyPrice.trade_date >= start_date,
            DailyPrice.trade_date <= end_date,
        )
        .order_by(DailyPrice.trade_date)
        .all()
    )

    return [
        {
            "trade_date": row.trade_date,
            "open_cents": row.open_cents,
            "high_cents": row.high_cents,
            "low_cents": row.low_cents,
            "close_cents": row.close_cents,
            "adj_close_cents": row.adj_close_cents,
            "volume": row.volume,
            "source": row.source,
        }
        for row in rows
    ]


def _store_prices(db_session: Session, ticker: str, prices: list[dict[str, Any]]) -> None:
    """Store downloaded prices in DailyPrice table (INSERT ON CONFLICT DO NOTHING).

    Args:
        db_session: SQLAlchemy session.
        ticker: Stock ticker symbol.
        prices: List of price dicts to cache.
    """
    for p in prices:
        # Check for existing row to emulate ON CONFLICT DO NOTHING
        existing = (
            db_session.query(DailyPrice)
            .filter(
                DailyPrice.ticker == ticker,
                DailyPrice.trade_date == p["trade_date"],
                DailyPrice.source == p["source"],
            )
            .first()
        )
        if existing is not None:
            continue

        td = p["trade_date"]
        row = DailyPrice(
            ticker=ticker,
            trade_date=p["trade_date"],
            open_cents=p["open_cents"],
            high_cents=p["high_cents"],
            low_cents=p["low_cents"],
            close_cents=p["close_cents"],
            adj_close_cents=p["adj_close_cents"],
            volume=p["volume"],
            source=p["source"],
            as_of_date=datetime(td.year, td.month, td.day, tzinfo=UTC),
        )
        db_session.add(row)

    db_session.commit()


@enforce_as_of_date
def get_price_history(
    ticker: str,
    *,
    as_of_date: date,
    lookback_days: int = 252,
    db_session: Session | None = None,
    settings: AppSettings | None = None,
) -> dict[str, Any]:
    """Get historical price data with cache-first pattern.

    Checks the DailyPrice cache table before calling external APIs.
    Computes period return, annualized volatility, 52-week high/low,
    and average volume. Returns a natural language summary for LLM
    consumption via format_price_summary.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL").
        as_of_date: Temporal cutoff date (enforced by decorator).
        lookback_days: Number of calendar days to look back (default 252 ~ 1 year).
        db_session: Optional SQLAlchemy session for cache reads/writes.
        settings: Optional AppSettings for API keys.

    Returns:
        Dict with keys: ticker, prices, summary_text, stats.
    """
    if settings is None:
        settings = get_settings()

    start_date = as_of_date - timedelta(days=lookback_days)

    # --- Cache check ---
    prices: list[dict[str, Any]] = []

    if db_session is not None:
        cached = _query_cached_prices(db_session, ticker, start_date, as_of_date)

        # >80% of expected trading days (~252 cal days * 5/7 = ~180 trading days)
        expected_trading_days = int(lookback_days * 5 / 7)
        cache_threshold = int(expected_trading_days * 0.80)

        if len(cached) >= cache_threshold:
            prices = cached

    # --- Cache miss: fetch from external APIs ---
    if not prices:
        client = PriceClient(tiingo_api_key=settings.tiingo_api_key)
        downloaded = client.download(ticker, start_date, as_of_date)

        # Filter to ensure temporal correctness
        prices = [p for p in downloaded if p["trade_date"] <= as_of_date]

        # Store in cache for future use
        if db_session is not None and prices:
            _store_prices(db_session, ticker, prices)

    # --- Compute stats ---
    sorted_prices = sorted(prices, key=lambda p: p["trade_date"])
    stats = _compute_stats(sorted_prices)

    # --- Generate NL summary ---
    avg_volume = (
        sum(p["volume"] for p in sorted_prices) // len(sorted_prices) if sorted_prices else 0
    )

    current_price_cents = sorted_prices[-1]["adj_close_cents"] if sorted_prices else 0

    summary_text = format_price_summary(
        ticker=ticker,
        current_price_cents=current_price_cents,
        period_return_pct=stats["return_pct"],
        annualized_volatility_pct=stats["volatility_pct"],
        high_52w_cents=stats["high_52w_cents"],
        low_52w_cents=stats["low_52w_cents"],
        avg_volume=avg_volume,
        as_of_date=as_of_date,
    )

    return {
        "ticker": ticker,
        "prices": sorted_prices,
        "summary_text": summary_text,
        "stats": stats,
    }
