"""Agent-callable news sentiment tool with as_of_date enforcement.

Provides daily sentiment context (news headlines, sentiment scores)
for a given ticker, complementing fundamental and price data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings, get_settings
from ai_hedge_fund.data.clients.finnhub_client import FinnhubClient
from ai_hedge_fund.data.summary import format_news_summary
from ai_hedge_fund.data.temporal import enforce_as_of_date
from ai_hedge_fund.db.models import NewsArticle

logger = structlog.get_logger(__name__)


@enforce_as_of_date
def get_news_sentiment(
    ticker: str,
    *,
    as_of_date: date,
    lookback_days: int = 7,
    db_session: Session | None = None,
    settings: AppSettings | None = None,
) -> dict[str, Any]:
    """Retrieve daily news sentiment for a ticker.

    Fetches company news from Finnhub within the lookback window,
    filters articles to exclude future data, computes average sentiment,
    and produces a natural language summary for agent consumption.

    Args:
        ticker: Stock ticker symbol.
        as_of_date: Temporal cutoff date. Articles after this date are excluded.
        lookback_days: Number of days before as_of_date to include (default 7).
        db_session: Optional SQLAlchemy session for caching articles.
        settings: Optional AppSettings instance. Created from env if not provided.

    Returns:
        Dict with keys: ticker, articles, avg_sentiment, summary_text.

    Raises:
        ValueError: If as_of_date is None or finnhub_api_key is not configured.
    """
    resolved_settings = settings if settings is not None else get_settings()

    if not resolved_settings.finnhub_api_key:
        msg = "finnhub_api_key is required -- set FINNHUB_API_KEY in .env"
        raise ValueError(msg)

    client = FinnhubClient(api_key=resolved_settings.finnhub_api_key)

    from_date = as_of_date - timedelta(days=lookback_days)
    raw_articles = client.get_company_news(
        ticker=ticker,
        from_date=from_date,
        to_date=as_of_date,
    )

    # Filter articles published after as_of_date (temporal enforcement)
    cutoff = datetime(
        as_of_date.year,
        as_of_date.month,
        as_of_date.day,
        23,
        59,
        59,
        tzinfo=UTC,
    )
    filtered_articles = [a for a in raw_articles if a["published_date"] <= cutoff]

    # Compute average sentiment (ignoring None values)
    scored = [a["sentiment_score"] for a in filtered_articles if a["sentiment_score"] is not None]
    avg_sentiment: float | None = sum(scored) / len(scored) if scored else None

    # Cache to database if session provided
    if db_session is not None:
        _cache_articles(ticker, filtered_articles, db_session)

    # Generate natural language summary
    # Replace None sentiment_score with 0.0 for the summary formatter
    # (original articles list retains None values for transparency)
    summary_articles = [
        {**a, "sentiment_score": a["sentiment_score"] if a["sentiment_score"] is not None else 0.0}
        for a in filtered_articles
    ]
    summary_text = format_news_summary(
        ticker=ticker,
        articles=summary_articles,
        as_of_date=as_of_date,
    )

    return {
        "ticker": ticker,
        "articles": filtered_articles,
        "avg_sentiment": avg_sentiment,
        "summary_text": summary_text,
    }


def _cache_articles(
    ticker: str,
    articles: list[dict[str, Any]],
    db_session: Session,
) -> None:
    """Cache articles to NewsArticle model (INSERT ON CONFLICT DO NOTHING).

    Args:
        ticker: Stock ticker symbol.
        articles: List of standardized article dicts.
        db_session: Active SQLAlchemy session.
    """
    for article in articles:
        # Check if article already exists (ticker + url uniqueness)
        existing = (
            db_session.query(NewsArticle).filter_by(ticker=ticker, url=article["url"]).first()
        )
        if existing is not None:
            continue

        record = NewsArticle(
            ticker=ticker,
            headline=article["headline"],
            source=article["source"],
            url=article["url"],
            sentiment_score=article["sentiment_score"],
            published_date=article["published_date"],
            as_of_date=date.today(),
            observed_date=date.today(),
        )
        db_session.add(record)

    db_session.flush()
