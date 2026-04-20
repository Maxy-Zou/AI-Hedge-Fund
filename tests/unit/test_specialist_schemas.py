"""Tests for specialist analyst output schemas (Phase 4, Plan 01, Task 1).

Covers: ValuationMetric, FilingCitation, FundamentalAnalysis,
SentimentComponent, SentimentAnalysis, TechnicalIndicator,
TechnicalAnalysis, AnalystReport.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestValuationMetric:
    """Tests for ValuationMetric sub-model."""

    def test_valid_valuation_metric(self) -> None:
        """ValuationMetric validates with all required fields."""
        from ai_hedge_fund.schemas.agents import ValuationMetric

        m = ValuationMetric(
            metric_name="P/E Ratio",
            value="15.2",
            source_tool="get_financials",
        )
        assert m.metric_name == "P/E Ratio"
        assert m.value == "15.2"
        assert m.source_tool == "get_financials"

    def test_rejects_empty_metric_name(self) -> None:
        """ValuationMetric rejects empty metric_name."""
        from ai_hedge_fund.schemas.agents import ValuationMetric

        with pytest.raises(ValidationError):
            ValuationMetric(metric_name="", value="15.2", source_tool="get_financials")

    def test_rejects_empty_source_tool(self) -> None:
        """ValuationMetric rejects empty source_tool."""
        from ai_hedge_fund.schemas.agents import ValuationMetric

        with pytest.raises(ValidationError):
            ValuationMetric(metric_name="P/E", value="15.2", source_tool="")


class TestFilingCitation:
    """Tests for FilingCitation sub-model."""

    def test_valid_filing_citation(self) -> None:
        """FilingCitation validates with all required fields."""
        from ai_hedge_fund.schemas.agents import FilingCitation

        c = FilingCitation(
            form_type="10-K",
            section="Risk Factors",
            key_quote="The company faces significant competition...",
            filing_date="2024-03-15",
        )
        assert c.form_type == "10-K"
        assert c.section == "Risk Factors"
        assert c.filing_date == "2024-03-15"


class TestFundamentalAnalysis:
    """Tests for FundamentalAnalysis specialist output schema."""

    def _valid_metrics(self, count: int = 2) -> list[dict]:
        return [
            {"metric_name": f"Metric {i}", "value": f"{10 + i}", "source_tool": "get_financials"}
            for i in range(count)
        ]

    def _valid_citations(self, count: int = 1) -> list[dict]:
        return [
            {
                "form_type": "10-K",
                "section": f"Section {i}",
                "key_quote": f"Quote {i}",
                "filing_date": "2024-03-15",
            }
            for i in range(count)
        ]

    def test_valid_fundamental_analysis(self) -> None:
        """FundamentalAnalysis validates with all required fields at minimum lengths."""
        from ai_hedge_fund.schemas.agents import FundamentalAnalysis

        fa = FundamentalAnalysis(
            ticker="AAPL",
            valuation_assessment="Fairly valued based on DCF analysis",
            valuation_metrics=self._valid_metrics(2),
            filing_citations=self._valid_citations(1),
            bull_factors=["Strong revenue growth"],
            bear_factors=["Increasing competition"],
            confidence=75,
        )
        assert fa.ticker == "AAPL"
        assert len(fa.valuation_metrics) == 2
        assert len(fa.filing_citations) == 1
        assert fa.confidence == 75

    def test_rejects_zero_valuation_metrics(self) -> None:
        """FundamentalAnalysis rejects empty valuation_metrics (min_length=2)."""
        from ai_hedge_fund.schemas.agents import FundamentalAnalysis

        with pytest.raises(ValidationError):
            FundamentalAnalysis(
                ticker="AAPL",
                valuation_assessment="test",
                valuation_metrics=[],
                filing_citations=self._valid_citations(1),
                bull_factors=["x"],
                bear_factors=["x"],
                confidence=50,
            )

    def test_rejects_one_valuation_metric(self) -> None:
        """FundamentalAnalysis rejects valuation_metrics with only 1 item (min_length=2)."""
        from ai_hedge_fund.schemas.agents import FundamentalAnalysis

        with pytest.raises(ValidationError):
            FundamentalAnalysis(
                ticker="AAPL",
                valuation_assessment="test",
                valuation_metrics=self._valid_metrics(1),
                filing_citations=self._valid_citations(1),
                bull_factors=["x"],
                bear_factors=["x"],
                confidence=50,
            )

    def test_rejects_confidence_above_100(self) -> None:
        """FundamentalAnalysis rejects confidence > 100."""
        from ai_hedge_fund.schemas.agents import FundamentalAnalysis

        with pytest.raises(ValidationError):
            FundamentalAnalysis(
                ticker="AAPL",
                valuation_assessment="test",
                valuation_metrics=self._valid_metrics(2),
                filing_citations=self._valid_citations(1),
                bull_factors=["x"],
                bear_factors=["x"],
                confidence=101,
            )

    def test_rejects_confidence_below_zero(self) -> None:
        """FundamentalAnalysis rejects confidence < 0."""
        from ai_hedge_fund.schemas.agents import FundamentalAnalysis

        with pytest.raises(ValidationError):
            FundamentalAnalysis(
                ticker="AAPL",
                valuation_assessment="test",
                valuation_metrics=self._valid_metrics(2),
                filing_citations=self._valid_citations(1),
                bull_factors=["x"],
                bear_factors=["x"],
                confidence=-1,
            )

    def test_model_dump_produces_dict(self) -> None:
        """FundamentalAnalysis.model_dump() returns a dict."""
        from ai_hedge_fund.schemas.agents import FundamentalAnalysis

        fa = FundamentalAnalysis(
            ticker="AAPL",
            valuation_assessment="test",
            valuation_metrics=self._valid_metrics(2),
            filing_citations=self._valid_citations(1),
            bull_factors=["x"],
            bear_factors=["x"],
            confidence=50,
        )
        dumped = fa.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["ticker"] == "AAPL"
        assert len(dumped["valuation_metrics"]) == 2


class TestSentimentComponent:
    """Tests for SentimentComponent sub-model."""

    def test_valid_sentiment_component(self) -> None:
        """SentimentComponent validates with valid data."""
        from ai_hedge_fund.schemas.agents import SentimentComponent

        sc = SentimentComponent(
            component="news_sentiment",
            score=0.5,
            summary="Positive coverage about new product launch",
            source_tool="get_news_sentiment",
        )
        assert sc.score == 0.5
        assert sc.source_tool == "get_news_sentiment"

    def test_rejects_score_above_one(self) -> None:
        """SentimentComponent rejects score > 1.0."""
        from ai_hedge_fund.schemas.agents import SentimentComponent

        with pytest.raises(ValidationError):
            SentimentComponent(
                component="news_sentiment",
                score=1.5,
                summary="test",
                source_tool="get_news_sentiment",
            )

    def test_rejects_score_below_neg_one(self) -> None:
        """SentimentComponent rejects score < -1.0."""
        from ai_hedge_fund.schemas.agents import SentimentComponent

        with pytest.raises(ValidationError):
            SentimentComponent(
                component="news_sentiment",
                score=-1.5,
                summary="test",
                source_tool="get_news_sentiment",
            )

    def test_rejects_empty_source_tool(self) -> None:
        """SentimentComponent rejects empty source_tool."""
        from ai_hedge_fund.schemas.agents import SentimentComponent

        with pytest.raises(ValidationError):
            SentimentComponent(
                component="news_sentiment",
                score=0.3,
                summary="test",
                source_tool="",
            )


class TestSentimentAnalysis:
    """Tests for SentimentAnalysis specialist output schema."""

    def _valid_components(self, count: int = 1) -> list[dict]:
        return [
            {
                "component": f"component_{i}",
                "score": 0.3,
                "summary": f"Summary {i}",
                "source_tool": "get_news_sentiment",
            }
            for i in range(count)
        ]

    def test_valid_sentiment_analysis(self) -> None:
        """SentimentAnalysis validates with all required fields."""
        from ai_hedge_fund.schemas.agents import SentimentAnalysis

        sa = SentimentAnalysis(
            ticker="AAPL",
            composite_score=0.4,
            components=self._valid_components(2),
            key_signals=["Positive earnings coverage"],
            confidence=65,
        )
        assert sa.ticker == "AAPL"
        assert sa.composite_score == 0.4
        assert len(sa.components) == 2
        assert sa.confidence == 65

    def test_rejects_composite_score_above_one(self) -> None:
        """SentimentAnalysis rejects composite_score > 1.0."""
        from ai_hedge_fund.schemas.agents import SentimentAnalysis

        with pytest.raises(ValidationError):
            SentimentAnalysis(
                ticker="AAPL",
                composite_score=2.0,
                components=self._valid_components(1),
                key_signals=["x"],
                confidence=50,
            )

    def test_rejects_composite_score_below_neg_one(self) -> None:
        """SentimentAnalysis rejects composite_score < -1.0."""
        from ai_hedge_fund.schemas.agents import SentimentAnalysis

        with pytest.raises(ValidationError):
            SentimentAnalysis(
                ticker="AAPL",
                composite_score=-1.5,
                components=self._valid_components(1),
                key_signals=["x"],
                confidence=50,
            )

    def test_rejects_empty_components(self) -> None:
        """SentimentAnalysis rejects empty components list."""
        from ai_hedge_fund.schemas.agents import SentimentAnalysis

        with pytest.raises(ValidationError):
            SentimentAnalysis(
                ticker="AAPL",
                composite_score=0.3,
                components=[],
                key_signals=["x"],
                confidence=50,
            )

    def test_rejects_empty_key_signals(self) -> None:
        """SentimentAnalysis rejects empty key_signals list."""
        from ai_hedge_fund.schemas.agents import SentimentAnalysis

        with pytest.raises(ValidationError):
            SentimentAnalysis(
                ticker="AAPL",
                composite_score=0.3,
                components=self._valid_components(1),
                key_signals=[],
                confidence=50,
            )

    def test_model_dump_produces_dict(self) -> None:
        """SentimentAnalysis.model_dump() returns a dict."""
        from ai_hedge_fund.schemas.agents import SentimentAnalysis

        sa = SentimentAnalysis(
            ticker="AAPL",
            composite_score=0.4,
            components=self._valid_components(1),
            key_signals=["x"],
            confidence=50,
        )
        dumped = sa.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["composite_score"] == 0.4


class TestTechnicalIndicator:
    """Tests for TechnicalIndicator sub-model."""

    def test_valid_technical_indicator(self) -> None:
        """TechnicalIndicator validates with valid data."""
        from ai_hedge_fund.schemas.agents import TechnicalIndicator

        ti = TechnicalIndicator(
            indicator="RSI",
            value="65.3",
            interpretation="bullish",
            source_tool="get_price_data",
        )
        assert ti.indicator == "RSI"
        assert ti.source_tool == "get_price_data"

    def test_rejects_empty_source_tool(self) -> None:
        """TechnicalIndicator rejects empty source_tool."""
        from ai_hedge_fund.schemas.agents import TechnicalIndicator

        with pytest.raises(ValidationError):
            TechnicalIndicator(
                indicator="RSI",
                value="65.3",
                interpretation="bullish",
                source_tool="",
            )


class TestTechnicalAnalysis:
    """Tests for TechnicalAnalysis specialist output schema."""

    def _valid_indicators(self, count: int = 2) -> list[dict]:
        return [
            {
                "indicator": f"Indicator {i}",
                "value": f"{50 + i}",
                "interpretation": "bullish",
                "source_tool": "get_price_data",
            }
            for i in range(count)
        ]

    def test_valid_technical_analysis(self) -> None:
        """TechnicalAnalysis validates with all required fields at minimum lengths."""
        from ai_hedge_fund.schemas.agents import TechnicalAnalysis

        ta = TechnicalAnalysis(
            ticker="AAPL",
            momentum_assessment="Bullish momentum with RSI above 50",
            volatility_assessment="Moderate volatility within normal range",
            indicators=self._valid_indicators(2),
            bull_factors=["Positive momentum"],
            bear_factors=["Overbought conditions"],
            confidence=60,
        )
        assert ta.ticker == "AAPL"
        assert len(ta.indicators) == 2
        assert ta.confidence == 60

    def test_rejects_zero_indicators(self) -> None:
        """TechnicalAnalysis rejects empty indicators (min_length=2)."""
        from ai_hedge_fund.schemas.agents import TechnicalAnalysis

        with pytest.raises(ValidationError):
            TechnicalAnalysis(
                ticker="AAPL",
                momentum_assessment="test",
                volatility_assessment="test",
                indicators=[],
                bull_factors=["x"],
                bear_factors=["x"],
                confidence=50,
            )

    def test_rejects_one_indicator(self) -> None:
        """TechnicalAnalysis rejects indicators with only 1 item (min_length=2)."""
        from ai_hedge_fund.schemas.agents import TechnicalAnalysis

        with pytest.raises(ValidationError):
            TechnicalAnalysis(
                ticker="AAPL",
                momentum_assessment="test",
                volatility_assessment="test",
                indicators=self._valid_indicators(1),
                bull_factors=["x"],
                bear_factors=["x"],
                confidence=50,
            )

    def test_rejects_confidence_above_100(self) -> None:
        """TechnicalAnalysis rejects confidence > 100."""
        from ai_hedge_fund.schemas.agents import TechnicalAnalysis

        with pytest.raises(ValidationError):
            TechnicalAnalysis(
                ticker="AAPL",
                momentum_assessment="test",
                volatility_assessment="test",
                indicators=self._valid_indicators(2),
                bull_factors=["x"],
                bear_factors=["x"],
                confidence=101,
            )

    def test_model_dump_produces_dict(self) -> None:
        """TechnicalAnalysis.model_dump() returns a dict."""
        from ai_hedge_fund.schemas.agents import TechnicalAnalysis

        ta = TechnicalAnalysis(
            ticker="AAPL",
            momentum_assessment="test",
            volatility_assessment="test",
            indicators=self._valid_indicators(2),
            bull_factors=["x"],
            bear_factors=["x"],
            confidence=50,
        )
        dumped = ta.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["ticker"] == "AAPL"
        assert len(dumped["indicators"]) == 2


class TestAnalystReport:
    """Tests for AnalystReport wrapper schema."""

    def test_valid_analyst_report(self) -> None:
        """AnalystReport validates with valid data."""
        from ai_hedge_fund.schemas.agents import AnalystReport

        report = AnalystReport(
            analyst="fundamental",
            analysis={"ticker": "AAPL", "confidence": 75},
            tokens_used=5000,
        )
        assert report.analyst == "fundamental"
        assert report.tokens_used == 5000
        assert report.error is None

    def test_valid_analyst_report_with_error(self) -> None:
        """AnalystReport validates with error string."""
        from ai_hedge_fund.schemas.agents import AnalystReport

        report = AnalystReport(
            analyst="sentiment",
            analysis={},
            tokens_used=0,
            error="budget exceeded",
        )
        assert report.error == "budget exceeded"

    def test_rejects_invalid_analyst_literal(self) -> None:
        """AnalystReport rejects analyst not in Literal constraint."""
        from ai_hedge_fund.schemas.agents import AnalystReport

        with pytest.raises(ValidationError):
            AnalystReport(
                analyst="invalid",
                analysis={},
                tokens_used=0,
            )

    def test_rejects_negative_tokens_used(self) -> None:
        """AnalystReport rejects negative tokens_used."""
        from ai_hedge_fund.schemas.agents import AnalystReport

        with pytest.raises(ValidationError):
            AnalystReport(
                analyst="technical",
                analysis={},
                tokens_used=-1,
            )

    def test_all_valid_analyst_types(self) -> None:
        """AnalystReport accepts all three valid analyst types."""
        from ai_hedge_fund.schemas.agents import AnalystReport

        for analyst_type in ("fundamental", "sentiment", "technical"):
            report = AnalystReport(
                analyst=analyst_type,
                analysis={},
                tokens_used=100,
            )
            assert report.analyst == analyst_type
