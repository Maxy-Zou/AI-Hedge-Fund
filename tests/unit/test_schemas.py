"""Tests for LangGraph state schemas and PydanticAI output schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestPipelineState:
    """Tests for the LangGraph PipelineState TypedDict."""

    def test_instantiate_with_required_fields(self) -> None:
        """PipelineState can be instantiated with required and optional fields."""
        from ai_hedge_fund.schemas.state import PipelineState

        state: PipelineState = {
            "ticker": "AAPL",
            "raw_text": "Some filing text",
            "extraction": None,
            "analysis": None,
            "error": None,
        }
        assert state["ticker"] == "AAPL"
        assert state["raw_text"] == "Some filing text"
        assert state["extraction"] is None
        assert state["analysis"] is None
        assert state["error"] is None

    def test_instantiate_minimal(self) -> None:
        """PipelineState works with only required fields (total=False defaults)."""
        from ai_hedge_fund.schemas.state import PipelineState

        state: PipelineState = {
            "ticker": "MSFT",
            "raw_text": "10-K filing content",
        }
        assert state["ticker"] == "MSFT"


class TestExtractionOutput:
    """Tests for ExtractionOutput PydanticAI schema."""

    def test_valid_extraction(self) -> None:
        """ExtractionOutput validates with valid data."""
        from ai_hedge_fund.schemas.agents import ExtractionOutput

        output = ExtractionOutput(key_metrics=["revenue: $10B"], data_quality=0.85)
        assert output.key_metrics == ["revenue: $10B"]
        assert output.data_quality == 0.85

    def test_rejects_empty_key_metrics(self) -> None:
        """ExtractionOutput rejects empty key_metrics list."""
        from ai_hedge_fund.schemas.agents import ExtractionOutput

        with pytest.raises(ValidationError):
            ExtractionOutput(key_metrics=[], data_quality=0.5)

    def test_rejects_data_quality_above_one(self) -> None:
        """ExtractionOutput rejects data_quality > 1.0."""
        from ai_hedge_fund.schemas.agents import ExtractionOutput

        with pytest.raises(ValidationError):
            ExtractionOutput(key_metrics=["metric"], data_quality=1.1)

    def test_rejects_data_quality_below_zero(self) -> None:
        """ExtractionOutput rejects data_quality < 0.0."""
        from ai_hedge_fund.schemas.agents import ExtractionOutput

        with pytest.raises(ValidationError):
            ExtractionOutput(key_metrics=["metric"], data_quality=-0.1)

    def test_model_dump_produces_dict(self) -> None:
        """ExtractionOutput.model_dump() returns a clean dict."""
        from ai_hedge_fund.schemas.agents import ExtractionOutput

        output = ExtractionOutput(key_metrics=["revenue: $10B"], data_quality=0.9)
        dumped = output.model_dump()
        assert isinstance(dumped, dict)
        assert "key_metrics" in dumped
        assert "data_quality" in dumped


class TestAnalysisOutput:
    """Tests for AnalysisOutput PydanticAI schema."""

    def test_valid_analysis(self) -> None:
        """AnalysisOutput validates with valid data."""
        from ai_hedge_fund.schemas.agents import AnalysisOutput

        output = AnalysisOutput(
            summary="Strong quarterly results",
            confidence=0.7,
            key_findings=["Revenue grew 15% YoY"],
        )
        assert output.summary == "Strong quarterly results"
        assert output.confidence == 0.7

    def test_rejects_confidence_above_one(self) -> None:
        """AnalysisOutput rejects confidence > 1.0."""
        from ai_hedge_fund.schemas.agents import AnalysisOutput

        with pytest.raises(ValidationError):
            AnalysisOutput(
                summary="test",
                confidence=1.5,
                key_findings=["finding"],
            )

    def test_rejects_empty_key_findings(self) -> None:
        """AnalysisOutput rejects empty key_findings list."""
        from ai_hedge_fund.schemas.agents import AnalysisOutput

        with pytest.raises(ValidationError):
            AnalysisOutput(
                summary="test",
                confidence=0.5,
                key_findings=[],
            )

    def test_model_dump_produces_dict(self) -> None:
        """AnalysisOutput.model_dump() returns a clean dict."""
        from ai_hedge_fund.schemas.agents import AnalysisOutput

        output = AnalysisOutput(
            summary="test",
            confidence=0.8,
            key_findings=["finding1"],
        )
        dumped = output.model_dump()
        assert isinstance(dumped, dict)
        assert "summary" in dumped


def _valid_thesis_point(
    *,
    claim: str = "Strong iPhone demand",
    evidence: str = "Revenue grew 15% YoY in iPhone segment",
    source_tool: str = "get_financials",
) -> dict[str, str]:
    """Helper: Build a valid ThesisPoint-compatible dict."""
    return {"claim": claim, "evidence": evidence, "source_tool": source_tool}


class TestThesisPoint:
    """Tests for ThesisPoint sub-model (bull/bear case entries)."""

    def test_valid_thesis_point(self) -> None:
        """ThesisPoint validates with all required non-empty fields."""
        from ai_hedge_fund.schemas.agents import ThesisPoint

        point = ThesisPoint(
            claim="Strong iPhone demand",
            evidence="Revenue grew 15% YoY",
            source_tool="get_financials",
        )
        assert point.claim == "Strong iPhone demand"
        assert point.evidence == "Revenue grew 15% YoY"
        assert point.source_tool == "get_financials"

    def test_rejects_empty_claim(self) -> None:
        """ThesisPoint rejects empty claim string."""
        from ai_hedge_fund.schemas.agents import ThesisPoint

        with pytest.raises(ValidationError):
            ThesisPoint(claim="", evidence="x", source_tool="x")

    def test_rejects_empty_evidence(self) -> None:
        """ThesisPoint rejects empty evidence string."""
        from ai_hedge_fund.schemas.agents import ThesisPoint

        with pytest.raises(ValidationError):
            ThesisPoint(claim="x", evidence="", source_tool="x")

    def test_rejects_empty_source_tool(self) -> None:
        """ThesisPoint rejects empty source_tool string."""
        from ai_hedge_fund.schemas.agents import ThesisPoint

        with pytest.raises(ValidationError):
            ThesisPoint(claim="x", evidence="x", source_tool="")


class TestThesisOutput:
    """Tests for ThesisOutput PydanticAI schema (tightened for AGENT-03)."""

    def _thesis_points(self, count: int, source: str) -> list[dict[str, str]]:
        """Helper: Build `count` valid thesis points."""
        return [
            _valid_thesis_point(
                claim=f"{source} point {i}",
                evidence=f"{source} evidence {i}",
                source_tool="get_financials",
            )
            for i in range(count)
        ]

    def test_valid_thesis(self) -> None:
        """ThesisOutput validates with 3+ bull/bear points and 2+ risks."""
        from ai_hedge_fund.schemas.agents import ThesisOutput

        output = ThesisOutput(
            ticker="AAPL",
            bull_case=self._thesis_points(3, "bull"),
            bear_case=self._thesis_points(3, "bear"),
            confidence=75,
            risk_factors=["China trade tensions", "Regulatory scrutiny"],
        )
        assert output.ticker == "AAPL"
        assert output.confidence == 75
        assert len(output.bull_case) == 3
        assert len(output.bear_case) == 3
        assert len(output.risk_factors) == 2

    def test_rejects_confidence_above_100(self) -> None:
        """ThesisOutput rejects confidence > 100."""
        from ai_hedge_fund.schemas.agents import ThesisOutput

        with pytest.raises(ValidationError):
            ThesisOutput(
                ticker="AAPL",
                bull_case=self._thesis_points(3, "bull"),
                bear_case=self._thesis_points(3, "bear"),
                confidence=101,
                risk_factors=["r1", "r2"],
            )

    def test_rejects_confidence_below_zero(self) -> None:
        """ThesisOutput rejects confidence < 0."""
        from ai_hedge_fund.schemas.agents import ThesisOutput

        with pytest.raises(ValidationError):
            ThesisOutput(
                ticker="AAPL",
                bull_case=self._thesis_points(3, "bull"),
                bear_case=self._thesis_points(3, "bear"),
                confidence=-1,
                risk_factors=["r1", "r2"],
            )

    def test_rejects_bull_case_with_two_points(self) -> None:
        """ThesisOutput rejects bull_case with fewer than 3 ThesisPoints."""
        from ai_hedge_fund.schemas.agents import ThesisOutput

        with pytest.raises(ValidationError):
            ThesisOutput(
                ticker="AAPL",
                bull_case=self._thesis_points(2, "bull"),
                bear_case=self._thesis_points(3, "bear"),
                confidence=50,
                risk_factors=["r1", "r2"],
            )

    def test_rejects_bear_case_with_two_points(self) -> None:
        """ThesisOutput rejects bear_case with fewer than 3 ThesisPoints."""
        from ai_hedge_fund.schemas.agents import ThesisOutput

        with pytest.raises(ValidationError):
            ThesisOutput(
                ticker="AAPL",
                bull_case=self._thesis_points(3, "bull"),
                bear_case=self._thesis_points(2, "bear"),
                confidence=50,
                risk_factors=["r1", "r2"],
            )

    def test_rejects_risk_factors_with_one_item(self) -> None:
        """ThesisOutput rejects risk_factors with fewer than 2 items."""
        from ai_hedge_fund.schemas.agents import ThesisOutput

        with pytest.raises(ValidationError):
            ThesisOutput(
                ticker="AAPL",
                bull_case=self._thesis_points(3, "bull"),
                bear_case=self._thesis_points(3, "bear"),
                confidence=50,
                risk_factors=["only one"],
            )

    def test_model_dump_produces_dict_with_nested_thesis_points(self) -> None:
        """ThesisOutput.model_dump() produces a dict with nested ThesisPoint dicts."""
        from ai_hedge_fund.schemas.agents import ThesisOutput

        output = ThesisOutput(
            ticker="AAPL",
            bull_case=self._thesis_points(3, "bull"),
            bear_case=self._thesis_points(3, "bear"),
            confidence=50,
            risk_factors=["r1", "r2"],
        )
        dumped = output.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["ticker"] == "AAPL"
        # Nested ThesisPoints flatten to dicts
        assert isinstance(dumped["bull_case"], list)
        assert len(dumped["bull_case"]) == 3
        assert set(dumped["bull_case"][0].keys()) == {"claim", "evidence", "source_tool"}
        assert isinstance(dumped["bear_case"], list)
        assert len(dumped["bear_case"]) == 3
        assert set(dumped["bear_case"][0].keys()) == {"claim", "evidence", "source_tool"}


class TestSignalOutput:
    """Tests for SignalOutput PydanticAI schema."""

    def test_valid_signal(self) -> None:
        """SignalOutput validates with valid data."""
        from ai_hedge_fund.schemas.agents import SignalOutput

        output = SignalOutput(
            ticker="AAPL",
            direction="long",
            conviction="high",
            time_horizon="3-6 months",
            position_size_pct=5.0,
            thesis_summary="Strong fundamentals with catalyst",
        )
        assert output.direction == "long"
        assert output.conviction == "high"

    def test_rejects_invalid_direction(self) -> None:
        """SignalOutput rejects direction not in Literal['long','short','neutral']."""
        from ai_hedge_fund.schemas.agents import SignalOutput

        with pytest.raises(ValidationError):
            SignalOutput(
                ticker="AAPL",
                direction="buy",  # type: ignore[arg-type]
                conviction="high",
                time_horizon="3 months",
                position_size_pct=5.0,
                thesis_summary="test",
            )

    def test_rejects_position_size_above_100(self) -> None:
        """SignalOutput rejects position_size_pct > 100."""
        from ai_hedge_fund.schemas.agents import SignalOutput

        with pytest.raises(ValidationError):
            SignalOutput(
                ticker="AAPL",
                direction="long",
                conviction="medium",
                time_horizon="3 months",
                position_size_pct=101.0,
                thesis_summary="test",
            )

    def test_rejects_position_size_below_zero(self) -> None:
        """SignalOutput rejects position_size_pct < 0."""
        from ai_hedge_fund.schemas.agents import SignalOutput

        with pytest.raises(ValidationError):
            SignalOutput(
                ticker="AAPL",
                direction="neutral",
                conviction="low",
                time_horizon="1 month",
                position_size_pct=-1.0,
                thesis_summary="test",
            )

    def test_model_dump_produces_dict(self) -> None:
        """SignalOutput.model_dump() returns a clean dict."""
        from ai_hedge_fund.schemas.agents import SignalOutput

        output = SignalOutput(
            ticker="TSLA",
            direction="short",
            conviction="medium",
            time_horizon="6-12 months",
            position_size_pct=3.0,
            thesis_summary="Overvalued relative to peers",
        )
        dumped = output.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["direction"] == "short"
        assert dumped["position_size_pct"] == 3.0
