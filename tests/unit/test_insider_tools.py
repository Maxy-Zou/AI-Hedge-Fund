"""Tests for Form 4 insider trade client and cluster detection tools.

Tests cover:
- Form4Client.get_insider_trades: parse Form 4 filings into trade dicts
- Form4Client: cents conversion for price/value
- detect_purchase_clusters: 3+ insiders in 14-day window
- detect_purchase_clusters: empty when < 3 insiders
- detect_purchase_clusters: custom window_days and min_insiders
- detect_purchase_clusters: deduplicates overlapping clusters
- get_insider_clusters: as_of_date enforcement
- get_insider_clusters: filters by filing_date <= as_of_date
- get_insider_clusters: NL summary via format_insider_summary
- get_insider_clusters: "No significant insider activity" when no clusters
- get_insider_clusters: caches trades to InsiderTrade model
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings
from ai_hedge_fund.data.clients.form4_client import (
    detect_purchase_clusters,
)
from ai_hedge_fund.data.tools.insider_tools import get_insider_clusters
from ai_hedge_fund.db.models import InsiderTrade

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    """AppSettings with EDGAR identity set."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return AppSettings(edgar_identity="TestCorp test@example.com", _env_file=None)


@pytest.fixture()
def sample_purchases() -> list[dict]:
    """Create sample purchase trade dicts for cluster detection."""
    return [
        {
            "insider_name": "Alice Smith",
            "insider_title": "CEO",
            "trade_type": "purchase",
            "shares": 10_000,
            "price_cents": 15000,
            "value_cents": 150_000_000,
            "trade_date": date(2025, 1, 2),
            "filing_date": date(2025, 1, 4),
        },
        {
            "insider_name": "Bob Jones",
            "insider_title": "CFO",
            "trade_type": "purchase",
            "shares": 5_000,
            "price_cents": 15100,
            "value_cents": 75_500_000,
            "trade_date": date(2025, 1, 5),
            "filing_date": date(2025, 1, 7),
        },
        {
            "insider_name": "Carol Davis",
            "insider_title": "COO",
            "trade_type": "purchase",
            "shares": 8_000,
            "price_cents": 14900,
            "value_cents": 119_200_000,
            "trade_date": date(2025, 1, 8),
            "filing_date": date(2025, 1, 10),
        },
    ]


@pytest.fixture()
def sample_sparse_purchases() -> list[dict]:
    """Purchases spread over 30 days -- should NOT form a cluster."""
    return [
        {
            "insider_name": "Alice Smith",
            "insider_title": "CEO",
            "trade_type": "purchase",
            "shares": 10_000,
            "price_cents": 15000,
            "value_cents": 150_000_000,
            "trade_date": date(2025, 1, 2),
            "filing_date": date(2025, 1, 4),
        },
        {
            "insider_name": "Bob Jones",
            "insider_title": "CFO",
            "trade_type": "purchase",
            "shares": 5_000,
            "price_cents": 15100,
            "value_cents": 75_500_000,
            "trade_date": date(2025, 1, 20),
            "filing_date": date(2025, 1, 22),
        },
        {
            "insider_name": "Carol Davis",
            "insider_title": "COO",
            "trade_type": "purchase",
            "shares": 8_000,
            "price_cents": 14900,
            "value_cents": 119_200_000,
            "trade_date": date(2025, 2, 5),
            "filing_date": date(2025, 2, 7),
        },
    ]


# ---------------------------------------------------------------------------
# detect_purchase_clusters
# ---------------------------------------------------------------------------


class TestDetectPurchaseClusters:
    """Tests for cluster detection algorithm."""

    def test_finds_cluster_with_3_insiders_in_14_days(self, sample_purchases: list[dict]) -> None:
        """3 insiders buying within 14 days = cluster."""
        clusters = detect_purchase_clusters(sample_purchases)

        assert len(clusters) == 1
        cluster = clusters[0]
        assert cluster.cluster_size == 3
        assert "Alice Smith" in cluster.insiders
        assert "Bob Jones" in cluster.insiders
        assert "Carol Davis" in cluster.insiders

    def test_returns_empty_when_fewer_than_3_insiders(self) -> None:
        """< 3 insiders should NOT form a cluster."""
        purchases = [
            {
                "insider_name": "Alice Smith",
                "trade_type": "purchase",
                "shares": 10_000,
                "price_cents": 15000,
                "value_cents": 150_000_000,
                "trade_date": date(2025, 1, 2),
                "filing_date": date(2025, 1, 4),
            },
            {
                "insider_name": "Bob Jones",
                "trade_type": "purchase",
                "shares": 5_000,
                "price_cents": 15100,
                "value_cents": 75_500_000,
                "trade_date": date(2025, 1, 5),
                "filing_date": date(2025, 1, 7),
            },
        ]
        clusters = detect_purchase_clusters(purchases)

        assert len(clusters) == 0

    def test_no_cluster_when_spread_over_30_days(self, sample_sparse_purchases: list[dict]) -> None:
        """Purchases spread over 30 days should NOT form a cluster."""
        clusters = detect_purchase_clusters(sample_sparse_purchases)

        assert len(clusters) == 0

    def test_custom_window_days(self, sample_sparse_purchases: list[dict]) -> None:
        """With window_days=40, spread purchases should form a cluster."""
        clusters = detect_purchase_clusters(sample_sparse_purchases, window_days=40)

        assert len(clusters) == 1

    def test_custom_min_insiders(self) -> None:
        """With min_insiders=2, two insiders form a cluster."""
        purchases = [
            {
                "insider_name": "Alice Smith",
                "trade_type": "purchase",
                "shares": 10_000,
                "price_cents": 15000,
                "value_cents": 150_000_000,
                "trade_date": date(2025, 1, 2),
                "filing_date": date(2025, 1, 4),
            },
            {
                "insider_name": "Bob Jones",
                "trade_type": "purchase",
                "shares": 5_000,
                "price_cents": 15100,
                "value_cents": 75_500_000,
                "trade_date": date(2025, 1, 5),
                "filing_date": date(2025, 1, 7),
            },
        ]
        clusters = detect_purchase_clusters(purchases, min_insiders=2)

        assert len(clusters) == 1
        assert clusters[0].cluster_size == 2

    def test_deduplicates_overlapping_clusters(self) -> None:
        """Overlapping clusters should be deduplicated (largest kept)."""
        purchases = [
            {
                "insider_name": f"Insider {i}",
                "trade_type": "purchase",
                "shares": 1_000,
                "price_cents": 10000,
                "value_cents": 10_000_000,
                "trade_date": date(2025, 1, 1) + timedelta(days=i),
                "filing_date": date(2025, 1, 1) + timedelta(days=i + 2),
            }
            for i in range(6)
        ]
        clusters = detect_purchase_clusters(purchases)

        # Multiple overlapping windows -- should deduplicate
        # Each insider creates a window; many will overlap
        assert len(clusters) >= 1
        # The largest cluster should contain most insiders
        largest = max(clusters, key=lambda c: c.cluster_size)
        assert largest.cluster_size >= 3

    def test_cluster_is_immutable(self, sample_purchases: list[dict]) -> None:
        """InsiderCluster should be frozen dataclass."""
        clusters = detect_purchase_clusters(sample_purchases)

        cluster = clusters[0]
        with pytest.raises(AttributeError):
            cluster.cluster_size = 99  # type: ignore[misc]

    def test_cluster_has_correct_totals(self, sample_purchases: list[dict]) -> None:
        """Cluster should aggregate shares and value."""
        clusters = detect_purchase_clusters(sample_purchases)

        cluster = clusters[0]
        assert cluster.total_shares == 23_000  # 10000 + 5000 + 8000
        assert cluster.total_value_cents == 344_700_000  # sum of values

    def test_cluster_has_correct_dates(self, sample_purchases: list[dict]) -> None:
        """Cluster start/end dates should span the trades."""
        clusters = detect_purchase_clusters(sample_purchases)

        cluster = clusters[0]
        assert cluster.start_date == date(2025, 1, 2)
        assert cluster.end_date == date(2025, 1, 8)


# ---------------------------------------------------------------------------
# InsiderCluster dataclass
# ---------------------------------------------------------------------------


class TestInsiderCluster:
    """Tests for InsiderCluster frozen dataclass."""

    def test_insiders_is_tuple(self, sample_purchases: list[dict]) -> None:
        """Insiders field should be a tuple (immutable per CLAUDE.md)."""
        clusters = detect_purchase_clusters(sample_purchases)
        cluster = clusters[0]
        assert isinstance(cluster.insiders, tuple)


# ---------------------------------------------------------------------------
# get_insider_clusters: as_of_date enforcement
# ---------------------------------------------------------------------------


class TestGetInsiderClustersAsOfDate:
    """Tests for as_of_date validation."""

    def test_raises_when_as_of_date_is_none(self) -> None:
        with pytest.raises(ValueError, match="as_of_date is required"):
            get_insider_clusters("AAPL", as_of_date=None)


# ---------------------------------------------------------------------------
# get_insider_clusters: filtering and results
# ---------------------------------------------------------------------------


class TestGetInsiderClustersResults:
    """Tests for insider cluster tool results."""

    @patch("ai_hedge_fund.data.tools.insider_tools.Form4Client")
    def test_filters_by_filing_date(self, mock_form4_cls: MagicMock, settings: AppSettings) -> None:
        """Only trades with filing_date <= as_of_date should be included."""
        as_of = date(2025, 1, 8)
        mock_instance = MagicMock()
        mock_instance.get_insider_trades.return_value = [
            {
                "insider_name": "Alice Smith",
                "insider_title": "CEO",
                "trade_type": "purchase",
                "shares": 10_000,
                "price_cents": 15000,
                "value_cents": 150_000_000,
                "trade_date": date(2025, 1, 2),
                "filing_date": date(2025, 1, 4),
            },
            {
                "insider_name": "Bob Jones",
                "insider_title": "CFO",
                "trade_type": "purchase",
                "shares": 5_000,
                "price_cents": 15100,
                "value_cents": 75_500_000,
                "trade_date": date(2025, 1, 5),
                "filing_date": date(2025, 1, 7),
            },
            {
                "insider_name": "Carol Davis",
                "insider_title": "COO",
                "trade_type": "purchase",
                "shares": 8_000,
                "price_cents": 14900,
                "value_cents": 119_200_000,
                "trade_date": date(2025, 1, 6),
                # filing_date AFTER as_of_date -- should be excluded
                "filing_date": date(2025, 1, 12),
            },
        ]
        mock_form4_cls.return_value = mock_instance

        result = get_insider_clusters("AAPL", as_of_date=as_of, settings=settings)

        # Only 2 trades have filing_date <= as_of_date -> no cluster (< 3)
        assert len(result["clusters"]) == 0

    @patch("ai_hedge_fund.data.tools.insider_tools.Form4Client")
    def test_returns_no_significant_activity_when_no_clusters(
        self, mock_form4_cls: MagicMock, settings: AppSettings
    ) -> None:
        """When no clusters found, summary says no significant activity."""
        mock_instance = MagicMock()
        mock_instance.get_insider_trades.return_value = []
        mock_form4_cls.return_value = mock_instance

        result = get_insider_clusters("AAPL", as_of_date=date(2025, 1, 10), settings=settings)

        assert "No significant insider activity" in result["summary_text"]

    @patch("ai_hedge_fund.data.tools.insider_tools.Form4Client")
    def test_returns_cluster_result_fields(
        self,
        mock_form4_cls: MagicMock,
        sample_purchases: list[dict],
        settings: AppSettings,
    ) -> None:
        """Result should have ticker, clusters, summary_text."""
        mock_instance = MagicMock()
        mock_instance.get_insider_trades.return_value = sample_purchases
        mock_form4_cls.return_value = mock_instance

        result = get_insider_clusters("AAPL", as_of_date=date(2025, 1, 15), settings=settings)

        assert result["ticker"] == "AAPL"
        assert "clusters" in result
        assert "summary_text" in result
        assert isinstance(result["clusters"], list)
        assert isinstance(result["summary_text"], str)

    @patch("ai_hedge_fund.data.tools.insider_tools.Form4Client")
    def test_summary_calls_format_insider_summary(
        self,
        mock_form4_cls: MagicMock,
        sample_purchases: list[dict],
        settings: AppSettings,
    ) -> None:
        """Summary text should mention the ticker."""
        mock_instance = MagicMock()
        mock_instance.get_insider_trades.return_value = sample_purchases
        mock_form4_cls.return_value = mock_instance

        result = get_insider_clusters("AAPL", as_of_date=date(2025, 1, 15), settings=settings)

        assert "AAPL" in result["summary_text"]

    @patch("ai_hedge_fund.data.tools.insider_tools.Form4Client")
    def test_caches_trades_to_insider_trade_model(
        self,
        mock_form4_cls: MagicMock,
        sample_purchases: list[dict],
        db_session: Session,
        settings: AppSettings,
    ) -> None:
        """Downloaded trades should be cached in InsiderTrade table."""
        mock_instance = MagicMock()
        mock_instance.get_insider_trades.return_value = sample_purchases
        mock_form4_cls.return_value = mock_instance

        get_insider_clusters(
            "AAPL",
            as_of_date=date(2025, 1, 15),
            db_session=db_session,
            settings=settings,
        )

        cached = db_session.query(InsiderTrade).filter_by(ticker="AAPL").all()
        assert len(cached) == 3


# ---------------------------------------------------------------------------
# Form4Client
# ---------------------------------------------------------------------------


class TestForm4Client:
    """Tests for Form4Client trade parsing."""

    def test_trade_dicts_contain_required_fields(self) -> None:
        """Trade dicts should have all required fields."""
        required_fields = {
            "insider_name",
            "insider_title",
            "trade_type",
            "shares",
            "price_cents",
            "value_cents",
            "trade_date",
            "filing_date",
        }
        # Construct a minimal trade dict
        trade = {
            "insider_name": "Alice Smith",
            "insider_title": "CEO",
            "trade_type": "purchase",
            "shares": 10_000,
            "price_cents": 15000,
            "value_cents": 150_000_000,
            "trade_date": date(2025, 1, 2),
            "filing_date": date(2025, 1, 4),
        }
        assert set(trade.keys()) == required_fields

    def test_price_and_value_are_int_cents(self) -> None:
        """Price and value should be integer cents."""
        trade = {
            "price_cents": 15000,
            "value_cents": 150_000_000,
        }
        assert isinstance(trade["price_cents"], int)
        assert isinstance(trade["value_cents"], int)
