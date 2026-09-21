"""Tests for natural language summary formatters.

Validates that structured financial data (with monetary values in cents)
is formatted into readable prose for LLM consumption.
"""

from __future__ import annotations

from datetime import date

from ai_hedge_fund.data.summary import (
    format_financial_summary,
    format_insider_summary,
    format_macro_summary,
    format_news_summary,
    format_price_summary,
)


class TestFormatFinancialSummary:
    """Tests for format_financial_summary."""

    def test_produces_paragraph_with_key_metrics(self) -> None:
        result = format_financial_summary(
            ticker="AAPL",
            revenue_current_cents=394_300_000_000_00,  # $394.3B
            revenue_prior_cents=374_810_000_000_00,  # $374.81B
            net_income_current_cents=97_000_000_000_00,  # $97.0B
            net_income_prior_cents=89_730_000_000_00,  # $89.73B
            operating_margin_current=0.305,
            operating_margin_prior=0.298,
            fiscal_period="FY2025",
            eps_current=6.42,
            eps_prior=5.96,
        )
        assert "AAPL" in result
        assert "FY2025" in result
        assert "Revenue" in result or "revenue" in result
        assert "$394.3B" in result
        assert "Net income" in result or "net income" in result
        assert "30.5%" in result
        assert "EPS" in result or "eps" in result or "Diluted EPS" in result

    def test_handles_negative_net_income(self) -> None:
        result = format_financial_summary(
            ticker="RIVN",
            revenue_current_cents=12_000_000_000_00,  # $12.0B
            revenue_prior_cents=10_000_000_000_00,  # $10.0B
            net_income_current_cents=-5_000_000_000_00,  # -$5.0B (loss)
            net_income_prior_cents=-7_000_000_000_00,  # -$7.0B (loss)
            operating_margin_current=-0.15,
            operating_margin_prior=-0.25,
            fiscal_period="FY2024",
            eps_current=-2.50,
            eps_prior=-3.80,
        )
        assert "RIVN" in result
        assert "loss" in result.lower() or "-$" in result

    def test_monetary_values_formatted_as_dollars(self) -> None:
        result = format_financial_summary(
            ticker="TEST",
            revenue_current_cents=500_000_000_00,  # $500M
            revenue_prior_cents=450_000_000_00,
            net_income_current_cents=100_000_000_00,  # $100M
            net_income_prior_cents=90_000_000_00,
            operating_margin_current=0.20,
            operating_margin_prior=0.18,
            fiscal_period="FY2024",
            eps_current=2.00,
            eps_prior=1.80,
        )
        assert "$" in result

    def test_yoy_changes_included(self) -> None:
        result = format_financial_summary(
            ticker="AAPL",
            revenue_current_cents=394_300_000_000_00,
            revenue_prior_cents=374_810_000_000_00,
            net_income_current_cents=97_000_000_000_00,
            net_income_prior_cents=89_730_000_000_00,
            operating_margin_current=0.305,
            operating_margin_prior=0.298,
            fiscal_period="FY2025",
            eps_current=6.42,
            eps_prior=5.96,
        )
        # Should contain YoY percentage changes
        assert "%" in result
        assert "YoY" in result or "year-over-year" in result.lower()

    def test_percentages_formatted_to_one_decimal(self) -> None:
        result = format_financial_summary(
            ticker="TEST",
            revenue_current_cents=10_000_00,  # $100.00
            revenue_prior_cents=9_000_00,  # $90.00 -> ~11.1% growth
            net_income_current_cents=5_000_00,
            net_income_prior_cents=4_000_00,
            operating_margin_current=0.123456,
            operating_margin_prior=0.100,
            fiscal_period="Q1 2024",
            eps_current=1.00,
            eps_prior=0.90,
        )
        assert "12.3%" in result  # operating margin at 1 decimal


class TestFormatPriceSummary:
    """Tests for format_price_summary."""

    def test_produces_price_paragraph(self) -> None:
        result = format_price_summary(
            ticker="AAPL",
            current_price_cents=17_850,  # $178.50
            period_return_pct=12.5,
            annualized_volatility_pct=22.3,
            high_52w_cents=19_900,  # $199.00
            low_52w_cents=14_200,  # $142.00
            avg_volume=65_000_000,
            as_of_date=date(2024, 6, 15),
        )
        assert "AAPL" in result
        assert "$178.50" in result
        assert "12.5%" in result
        assert "22.3%" in result
        assert "$199.00" in result
        assert "$142.00" in result

    def test_monetary_values_as_dollars(self) -> None:
        result = format_price_summary(
            ticker="TEST",
            current_price_cents=5_000,  # $50.00
            period_return_pct=-5.0,
            annualized_volatility_pct=30.0,
            high_52w_cents=7_500,
            low_52w_cents=3_000,
            avg_volume=1_000_000,
            as_of_date=date(2024, 1, 1),
        )
        assert "$50.00" in result


class TestFormatInsiderSummary:
    """Tests for format_insider_summary."""

    def test_produces_cluster_paragraph(self) -> None:
        clusters = [
            {
                "insiders": ["John CEO", "Jane CFO", "Bob COO"],
                "total_shares": 150_000,
                "total_value_cents": 25_000_000_00,  # $25M
                "start_date": "2024-05-01",
                "end_date": "2024-05-10",
            }
        ]
        result = format_insider_summary(
            ticker="AAPL",
            clusters=clusters,
            as_of_date=date(2024, 6, 15),
        )
        assert "AAPL" in result
        assert "3" in result  # 3 insiders
        assert "150,000" in result or "150000" in result
        assert "$" in result

    def test_no_clusters_returns_no_activity(self) -> None:
        result = format_insider_summary(
            ticker="AAPL",
            clusters=[],
            as_of_date=date(2024, 6, 15),
        )
        assert "No significant insider activity" in result


class TestFormatNewsSummary:
    """Tests for format_news_summary."""

    def test_produces_sentiment_digest(self) -> None:
        articles = [
            {
                "headline": "Apple beats earnings estimates",
                "source": "Reuters",
                "sentiment_score": 0.8,
                "published_date": "2024-06-14",
            },
            {
                "headline": "iPhone sales slow in China",
                "source": "Bloomberg",
                "sentiment_score": -0.3,
                "published_date": "2024-06-14",
            },
        ]
        result = format_news_summary(
            ticker="AAPL",
            articles=articles,
            as_of_date=date(2024, 6, 15),
        )
        assert "AAPL" in result
        has_content = (
            "Apple beats earnings" in result or "Reuters" in result or "sentiment" in result.lower()
        )
        assert has_content

    def test_empty_articles_returns_no_news(self) -> None:
        result = format_news_summary(
            ticker="AAPL",
            articles=[],
            as_of_date=date(2024, 6, 15),
        )
        assert "No recent news" in result


class TestFormatMacroSummary:
    """Tests for format_macro_summary."""

    def test_produces_macro_paragraph(self) -> None:
        result = format_macro_summary(
            fed_funds_rate=5.25,
            cpi_yoy_pct=3.2,
            gdp_growth_pct=2.1,
            yield_spread=0.45,
            treasury_10y=4.25,
            as_of_date=date(2024, 6, 15),
        )
        assert "5.25%" in result or "5.2%" in result
        assert "3.2%" in result
        assert "2.1%" in result
        assert "fed" in result.lower() or "Federal" in result
