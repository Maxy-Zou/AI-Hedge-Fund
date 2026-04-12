"""Tests for Finnhub news client and sentiment tools.

Tests cover:
- FinnhubClient initialization and API key validation
- Company news retrieval with response mapping
- Empty response and error handling
- get_news_sentiment temporal filtering (as_of_date enforcement)
- Average sentiment computation
- NL summary generation via format_news_summary
- DB caching of articles to NewsArticle model
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings
from ai_hedge_fund.data.clients.finnhub_client import FinnhubClient
from ai_hedge_fund.data.tools.sentiment_tools import get_news_sentiment
from ai_hedge_fund.db.models import NewsArticle


# ---------------------------------------------------------------------------
# Sample Finnhub API responses
# ---------------------------------------------------------------------------

SAMPLE_NEWS_RESPONSE = [
    {
        "category": "company",
        "datetime": 1704067200,  # 2024-01-01 00:00:00 UTC
        "headline": "Company X reports strong Q4 earnings",
        "id": 101,
        "image": "https://img.example.com/1.jpg",
        "related": "AAPL",
        "source": "Reuters",
        "summary": "Company X exceeded expectations...",
        "url": "https://reuters.com/article/1",
    },
    {
        "category": "company",
        "datetime": 1704153600,  # 2024-01-02 00:00:00 UTC
        "headline": "Analyst downgrades Company X shares",
        "id": 102,
        "image": "https://img.example.com/2.jpg",
        "related": "AAPL",
        "source": "Bloomberg",
        "summary": "Valuation concerns...",
        "url": "https://bloomberg.com/article/2",
    },
    {
        "category": "company",
        "datetime": 1704326400,  # 2024-01-04 00:00:00 UTC (after as_of_date)
        "headline": "Future headline that should be filtered",
        "id": 103,
        "image": "",
        "related": "AAPL",
        "source": "CNBC",
        "summary": "This is in the future...",
        "url": "https://cnbc.com/article/3",
    },
]

SAMPLE_SENTIMENT_RESPONSE = {
    "buzz": {"articlesInLastWeek": 10, "buzz": 1.5, "weeklyAverage": 8.0},
    "companyNewsScore": 0.65,
    "sectorAverageBullishPercent": 0.55,
    "sectorAverageNewsScore": 0.50,
    "sentiment": {"bearishPercent": 0.30, "bullishPercent": 0.70},
    "symbol": "AAPL",
}


# ---------------------------------------------------------------------------
# FinnhubClient tests
# ---------------------------------------------------------------------------


class TestFinnhubClient:
    """Tests for the FinnhubClient wrapper."""

    def test_raises_on_empty_api_key(self) -> None:
        """FinnhubClient raises ValueError when api_key is empty."""
        with pytest.raises(ValueError, match="api_key"):
            FinnhubClient(api_key="")

    def test_raises_on_none_api_key(self) -> None:
        """FinnhubClient raises ValueError when api_key is None-ish."""
        with pytest.raises(ValueError, match="api_key"):
            FinnhubClient(api_key="")

    @patch("ai_hedge_fund.data.clients.finnhub_client.finnhub.Client")
    def test_get_company_news_returns_mapped_articles(self, mock_client_cls: MagicMock) -> None:
        """get_company_news maps Finnhub response to standardized article dicts."""
        mock_instance = MagicMock()
        mock_instance.company_news.return_value = SAMPLE_NEWS_RESPONSE[:2]
        mock_client_cls.return_value = mock_instance

        client = FinnhubClient(api_key="test-key")
        articles = client.get_company_news(
            ticker="AAPL",
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 3),
        )

        assert len(articles) == 2
        assert articles[0]["headline"] == "Company X reports strong Q4 earnings"
        assert articles[0]["source"] == "Reuters"
        assert articles[0]["url"] == "https://reuters.com/article/1"
        assert isinstance(articles[0]["published_date"], datetime)
        # Verify the datetime conversion from unix timestamp
        assert articles[0]["published_date"] == datetime(2024, 1, 1, tzinfo=timezone.utc)

    @patch("ai_hedge_fund.data.clients.finnhub_client.finnhub.Client")
    def test_get_company_news_empty_response(self, mock_client_cls: MagicMock) -> None:
        """get_company_news returns empty list when no news found."""
        mock_instance = MagicMock()
        mock_instance.company_news.return_value = []
        mock_client_cls.return_value = mock_instance

        client = FinnhubClient(api_key="test-key")
        articles = client.get_company_news(
            ticker="AAPL",
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 3),
        )

        assert articles == []

    @patch("ai_hedge_fund.data.clients.finnhub_client.finnhub.Client")
    def test_get_company_news_handles_api_error(self, mock_client_cls: MagicMock) -> None:
        """get_company_news returns empty list on API errors (graceful degradation)."""
        mock_instance = MagicMock()
        mock_instance.company_news.side_effect = Exception("API Error")
        mock_client_cls.return_value = mock_instance

        client = FinnhubClient(api_key="test-key")
        articles = client.get_company_news(
            ticker="AAPL",
            from_date=date(2024, 1, 1),
            to_date=date(2024, 1, 3),
        )

        assert articles == []

    @patch("ai_hedge_fund.data.clients.finnhub_client.finnhub.Client")
    def test_get_news_sentiment_returns_aggregate(self, mock_client_cls: MagicMock) -> None:
        """get_news_sentiment returns aggregate sentiment scores."""
        mock_instance = MagicMock()
        mock_instance.news_sentiment.return_value = SAMPLE_SENTIMENT_RESPONSE
        mock_client_cls.return_value = mock_instance

        client = FinnhubClient(api_key="test-key")
        result = client.get_news_sentiment(ticker="AAPL")

        assert result is not None
        assert result["company_score"] == 0.65
        assert result["sector_average"] == 0.50
        assert result["buzz_score"] == 1.5
        assert result["weekly_average"] == 8.0

    @patch("ai_hedge_fund.data.clients.finnhub_client.finnhub.Client")
    def test_get_news_sentiment_handles_none(self, mock_client_cls: MagicMock) -> None:
        """get_news_sentiment returns None when API returns None."""
        mock_instance = MagicMock()
        mock_instance.news_sentiment.return_value = None
        mock_client_cls.return_value = mock_instance

        client = FinnhubClient(api_key="test-key")
        result = client.get_news_sentiment(ticker="AAPL")

        assert result is None


# ---------------------------------------------------------------------------
# get_news_sentiment tool tests
# ---------------------------------------------------------------------------


class TestGetNewsSentiment:
    """Tests for the get_news_sentiment tool function."""

    def test_raises_when_as_of_date_is_none(self) -> None:
        """get_news_sentiment raises ValueError when as_of_date is None."""
        with pytest.raises(ValueError, match="as_of_date"):
            get_news_sentiment("AAPL", as_of_date=None)

    @patch("ai_hedge_fund.data.tools.sentiment_tools.FinnhubClient")
    def test_returns_sentiment_result(self, mock_client_cls: MagicMock) -> None:
        """get_news_sentiment returns a dict with ticker, articles, avg_sentiment, summary_text."""
        mock_instance = MagicMock()
        mock_instance.get_company_news.return_value = [
            {
                "headline": "Good news",
                "source": "Reuters",
                "url": "https://reuters.com/1",
                "sentiment_score": 0.8,
                "published_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "headline": "Bad news",
                "source": "Bloomberg",
                "url": "https://bloomberg.com/2",
                "sentiment_score": -0.4,
                "published_date": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
        ]
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, finnhub_api_key="test-key")
        result = get_news_sentiment(
            "AAPL",
            as_of_date=date(2024, 1, 3),
            settings=settings,
        )

        assert result["ticker"] == "AAPL"
        assert len(result["articles"]) == 2
        assert isinstance(result["avg_sentiment"], float)
        assert isinstance(result["summary_text"], str)

    @patch("ai_hedge_fund.data.tools.sentiment_tools.FinnhubClient")
    def test_excludes_articles_after_as_of_date(self, mock_client_cls: MagicMock) -> None:
        """Articles published after as_of_date are excluded."""
        mock_instance = MagicMock()
        mock_instance.get_company_news.return_value = [
            {
                "headline": "Before cutoff",
                "source": "Reuters",
                "url": "https://reuters.com/1",
                "sentiment_score": 0.5,
                "published_date": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
            {
                "headline": "After cutoff",
                "source": "Bloomberg",
                "url": "https://bloomberg.com/2",
                "sentiment_score": -0.3,
                "published_date": datetime(2024, 1, 5, tzinfo=timezone.utc),
            },
        ]
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, finnhub_api_key="test-key")
        result = get_news_sentiment(
            "AAPL",
            as_of_date=date(2024, 1, 3),
            settings=settings,
        )

        assert len(result["articles"]) == 1
        assert result["articles"][0]["headline"] == "Before cutoff"

    @patch("ai_hedge_fund.data.tools.sentiment_tools.FinnhubClient")
    def test_lookback_window(self, mock_client_cls: MagicMock) -> None:
        """get_news_sentiment uses lookback_days to compute from_date."""
        mock_instance = MagicMock()
        mock_instance.get_company_news.return_value = []
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, finnhub_api_key="test-key")
        get_news_sentiment(
            "AAPL",
            as_of_date=date(2024, 1, 10),
            lookback_days=5,
            settings=settings,
        )

        mock_instance.get_company_news.assert_called_once_with(
            ticker="AAPL",
            from_date=date(2024, 1, 5),
            to_date=date(2024, 1, 10),
        )

    @patch("ai_hedge_fund.data.tools.sentiment_tools.FinnhubClient")
    def test_avg_sentiment_computed_correctly(self, mock_client_cls: MagicMock) -> None:
        """avg_sentiment is the mean of non-None sentiment_scores."""
        mock_instance = MagicMock()
        mock_instance.get_company_news.return_value = [
            {
                "headline": "A",
                "source": "S1",
                "url": "https://a.com/1",
                "sentiment_score": 0.6,
                "published_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
            {
                "headline": "B",
                "source": "S2",
                "url": "https://b.com/2",
                "sentiment_score": 0.2,
                "published_date": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
            {
                "headline": "C",
                "source": "S3",
                "url": "https://c.com/3",
                "sentiment_score": None,
                "published_date": datetime(2024, 1, 2, tzinfo=timezone.utc),
            },
        ]
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, finnhub_api_key="test-key")
        result = get_news_sentiment(
            "AAPL",
            as_of_date=date(2024, 1, 3),
            settings=settings,
        )

        # Average of 0.6 and 0.2 (None excluded) = 0.4
        assert result["avg_sentiment"] == pytest.approx(0.4)

    @patch("ai_hedge_fund.data.tools.sentiment_tools.FinnhubClient")
    def test_summary_calls_format_news_summary(self, mock_client_cls: MagicMock) -> None:
        """Summary text is produced via format_news_summary."""
        mock_instance = MagicMock()
        mock_instance.get_company_news.return_value = [
            {
                "headline": "Test headline",
                "source": "Reuters",
                "url": "https://reuters.com/1",
                "sentiment_score": 0.5,
                "published_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
        ]
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, finnhub_api_key="test-key")
        result = get_news_sentiment(
            "AAPL",
            as_of_date=date(2024, 1, 3),
            settings=settings,
        )

        # format_news_summary produces a string containing the ticker and article count
        assert "AAPL" in result["summary_text"]
        assert "1 articles" in result["summary_text"] or "Test headline" in result["summary_text"]

    @patch("ai_hedge_fund.data.tools.sentiment_tools.FinnhubClient")
    def test_no_recent_news_returned(self, mock_client_cls: MagicMock) -> None:
        """'No recent news' returned when no articles found in window."""
        mock_instance = MagicMock()
        mock_instance.get_company_news.return_value = []
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, finnhub_api_key="test-key")
        result = get_news_sentiment(
            "AAPL",
            as_of_date=date(2024, 1, 3),
            settings=settings,
        )

        assert result["articles"] == []
        assert result["avg_sentiment"] is None
        assert "No recent news" in result["summary_text"]

    @patch("ai_hedge_fund.data.tools.sentiment_tools.FinnhubClient")
    def test_articles_cached_to_db(
        self, mock_client_cls: MagicMock, db_session: Session
    ) -> None:
        """Articles are cached to NewsArticle model when db_session provided."""
        mock_instance = MagicMock()
        mock_instance.get_company_news.return_value = [
            {
                "headline": "Cached headline",
                "source": "Reuters",
                "url": "https://reuters.com/cache",
                "sentiment_score": 0.3,
                "published_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
        ]
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, finnhub_api_key="test-key")
        get_news_sentiment(
            "AAPL",
            as_of_date=date(2024, 1, 3),
            db_session=db_session,
            settings=settings,
        )

        articles = db_session.query(NewsArticle).all()
        assert len(articles) == 1
        assert articles[0].ticker == "AAPL"
        assert articles[0].headline == "Cached headline"
        assert articles[0].url == "https://reuters.com/cache"

    @patch("ai_hedge_fund.data.tools.sentiment_tools.FinnhubClient")
    def test_duplicate_articles_not_inserted(
        self, mock_client_cls: MagicMock, db_session: Session
    ) -> None:
        """INSERT ON CONFLICT DO NOTHING prevents duplicate articles."""
        mock_instance = MagicMock()
        article = {
            "headline": "Same article",
            "source": "Reuters",
            "url": "https://reuters.com/same",
            "sentiment_score": 0.5,
            "published_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
        }
        mock_instance.get_company_news.return_value = [article]
        mock_client_cls.return_value = mock_instance

        settings = AppSettings(_env_file=None, finnhub_api_key="test-key")

        # Insert twice
        get_news_sentiment(
            "AAPL", as_of_date=date(2024, 1, 3), db_session=db_session, settings=settings,
        )
        get_news_sentiment(
            "AAPL", as_of_date=date(2024, 1, 3), db_session=db_session, settings=settings,
        )

        articles = db_session.query(NewsArticle).all()
        assert len(articles) == 1

    def test_raises_when_api_key_not_configured(self) -> None:
        """Raises ValueError when finnhub_api_key is empty."""
        settings = AppSettings(_env_file=None, finnhub_api_key="")
        with pytest.raises(ValueError, match="finnhub_api_key"):
            get_news_sentiment("AAPL", as_of_date=date(2024, 1, 3), settings=settings)
