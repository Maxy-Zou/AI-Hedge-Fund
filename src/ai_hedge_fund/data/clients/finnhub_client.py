"""Finnhub API client for company news and sentiment retrieval.

Wraps the finnhub-python SDK with retry logic, error handling, and
standardized response mapping. API keys are loaded from AppSettings
and never logged.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import finnhub
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class FinnhubClient:
    """Client for Finnhub news and sentiment API.

    Args:
        api_key: Finnhub API key. Must be non-empty.

    Raises:
        ValueError: If api_key is empty.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            msg = "api_key is required -- configure finnhub_api_key in .env"
            raise ValueError(msg)
        self._client = finnhub.Client(api_key=api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=False)
    def _fetch_company_news(
        self, ticker: str, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        """Raw API call with retry logic."""
        return self._client.company_news(ticker, _from=str(from_date), to=str(to_date))

    def get_company_news(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> list[dict[str, Any]]:
        """Retrieve company news articles from Finnhub.

        Args:
            ticker: Stock ticker symbol.
            from_date: Start date for news window.
            to_date: End date for news window.

        Returns:
            List of article dicts with keys: headline, source, url,
            sentiment_score, published_date. Returns empty list on error.
        """
        try:
            raw_articles = self._fetch_company_news(ticker, from_date, to_date)
        except Exception:
            logger.warning(
                "finnhub_company_news_failed",
                ticker=ticker,
                from_date=str(from_date),
                to_date=str(to_date),
            )
            return []

        if not raw_articles:
            return []

        return [_map_article(article) for article in raw_articles]

    def get_news_sentiment(self, ticker: str) -> dict[str, Any] | None:
        """Retrieve aggregate news sentiment from Finnhub.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            Dict with buzz_score, weekly_average, company_score,
            sector_average, or None if unavailable.
        """
        try:
            raw = self._client.news_sentiment(ticker)
        except Exception:
            logger.warning("finnhub_news_sentiment_failed", ticker=ticker)
            return None

        if raw is None:
            return None

        buzz = raw.get("buzz", {})
        return {
            "buzz_score": buzz.get("buzz"),
            "weekly_average": buzz.get("weeklyAverage"),
            "company_score": raw.get("companyNewsScore"),
            "sector_average": raw.get("sectorAverageNewsScore"),
        }


def _map_article(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a raw Finnhub news response to a standardized article dict.

    Args:
        raw: Raw Finnhub response dict with keys: datetime, headline,
            source, url, summary, etc.

    Returns:
        Standardized dict with: headline, source, url, sentiment_score,
        published_date.
    """
    unix_ts = raw.get("datetime", 0)
    published_date = datetime.fromtimestamp(unix_ts, tz=UTC)

    return {
        "headline": raw.get("headline", ""),
        "source": raw.get("source", ""),
        "url": raw.get("url", ""),
        "sentiment_score": raw.get("sentiment"),
        "published_date": published_date,
    }
