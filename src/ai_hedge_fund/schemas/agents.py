"""PydanticAI output schemas for agent responses.

Each schema defines the typed, validated output for a specific agent type.
Pydantic Field constraints enforce data quality at the validation boundary:
- min_length prevents empty or under-populated lists
- ge/le constraints enforce numeric ranges
- Literal types restrict categorical values

These schemas are used as PydanticAI Agent output_type parameters and
are serialized via model_dump() for storage in LangGraph state dicts.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractionOutput(BaseModel):
    """Output from data extraction agents (Haiku tier).

    Captures key financial metrics extracted from filings with a
    quality score indicating extraction confidence.
    """

    key_metrics: list[str] = Field(
        min_length=1,
        description="Key financial metrics extracted from the filing",
    )
    data_quality: float = Field(
        ge=0.0,
        le=1.0,
        description="Quality score of extracted data (0.0 = unusable, 1.0 = perfect)",
    )


class AnalysisOutput(BaseModel):
    """Output from analysis agents (Sonnet tier).

    Captures an executive summary, confidence level, and key findings
    from the analytical review of extracted data.
    """

    summary: str = Field(
        description="Executive summary of the analysis",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in analysis conclusions (0.0 = no confidence, 1.0 = certain)",
    )
    key_findings: list[str] = Field(
        min_length=1,
        description="Key analytical findings with supporting evidence",
    )


class ThesisPoint(BaseModel):
    """A single bull or bear case point with evidence citation.

    Each ThesisPoint forces the agent to cite both the data that supports
    its claim (``evidence``) and the tool that produced that data
    (``source_tool``), enforcing the tool-first principle at the schema
    boundary (AGENT-02, AGENT-03).
    """

    claim: str = Field(
        min_length=1,
        description="The investment argument",
    )
    evidence: str = Field(
        min_length=1,
        description="Specific data supporting the claim",
    )
    source_tool: str = Field(
        min_length=1,
        description="Which tool provided the evidence (e.g., 'get_financials')",
    )


class ThesisOutput(BaseModel):
    """Output from thesis synthesis (investment research agent).

    Captures the structured investment thesis with cited bull/bear cases,
    a confidence score (0-100), and named risk factors. Constraints enforce
    AGENT-03 requirements: at least 3 bull points, 3 bear points, and 2
    risk factors, each bull/bear point backed by a ThesisPoint citation.
    """

    ticker: str = Field(
        description="Stock ticker symbol",
    )
    bull_case: list[ThesisPoint] = Field(
        min_length=3,
        description="Bull case arguments with evidence citations (minimum 3)",
    )
    bear_case: list[ThesisPoint] = Field(
        min_length=3,
        description="Bear case arguments with evidence citations (minimum 3)",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence score 0-100 in the thesis direction",
    )
    risk_factors: list[str] = Field(
        min_length=2,
        description="Named risk factors that could invalidate the thesis (minimum 2)",
    )


class SignalOutput(BaseModel):
    """Output from signal generation (final pipeline output).

    Captures the trade signal backed by the synthesized thesis,
    including direction, conviction, sizing, and summary.
    """

    ticker: str = Field(
        description="Stock ticker symbol",
    )
    direction: Literal["long", "short", "neutral"] = Field(
        description="Trade direction based on thesis",
    )
    conviction: Literal["low", "medium", "high"] = Field(
        description="Conviction level based on evidence strength",
    )
    time_horizon: str = Field(
        description="Expected time horizon for the trade (e.g., '3-6 months')",
    )
    position_size_pct: float = Field(
        ge=0.0,
        le=100.0,
        description="Suggested portfolio allocation percentage (0-100)",
    )
    thesis_summary: str = Field(
        description="One-paragraph summary of the investment thesis",
    )


# ---------------------------------------------------------------------------
# Phase 4: Specialist analyst output schemas
# ---------------------------------------------------------------------------


class ValuationMetric(BaseModel):
    """A single computed valuation metric with tool citation.

    Forces the agent to cite which tool produced the metric value,
    enforcing the tool-first principle (T-04-01).
    """

    metric_name: str = Field(
        min_length=1,
        description="e.g., 'P/E Ratio', 'EV/EBITDA'",
    )
    value: str = Field(
        description="The metric value as reported by the tool",
    )
    source_tool: str = Field(
        min_length=1,
        description="Tool that produced this metric",
    )


class FilingCitation(BaseModel):
    """Reference to a specific SEC filing section.

    Provides an evidence trail from the agent's conclusions back to
    the source filing, supporting auditability and transparency.
    """

    form_type: str = Field(
        description="e.g., '10-K', '10-Q'",
    )
    section: str = Field(
        description="Section name from the filing",
    )
    key_quote: str = Field(
        description="Relevant excerpt from the filing",
    )
    filing_date: str = Field(
        description="Date the filing was made",
    )


class FundamentalAnalysis(BaseModel):
    """Output from the Fundamental Analyst agent (MULTI-01).

    Captures valuation assessment with computed metrics, SEC filing
    citations, and bull/bear factors. Constraints enforce minimum
    evidence requirements: at least 2 valuation metrics and 1 filing
    citation, each metric citing its source tool.
    """

    ticker: str = Field(
        description="Stock ticker symbol",
    )
    valuation_assessment: str = Field(
        description="Overall valuation conclusion",
    )
    valuation_metrics: list[ValuationMetric] = Field(
        min_length=2,
        description="Computed valuation metrics with tool citations",
    )
    filing_citations: list[FilingCitation] = Field(
        min_length=1,
        description="Specific SEC filing sections cited",
    )
    bull_factors: list[str] = Field(
        min_length=1,
        description="Positive fundamental factors",
    )
    bear_factors: list[str] = Field(
        min_length=1,
        description="Negative fundamental factors",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence in fundamental assessment",
    )


class SentimentComponent(BaseModel):
    """A single component of the composite sentiment score.

    Each component cites its source tool so the manager can trace
    sentiment conclusions back to specific data (T-04-01).
    """

    component: str = Field(
        description="e.g., 'news_sentiment', 'insider_activity'",
    )
    score: float = Field(
        ge=-1.0,
        le=1.0,
        description="Score from -1 (bearish) to +1 (bullish)",
    )
    summary: str = Field(
        description="Brief explanation of the score",
    )
    source_tool: str = Field(
        min_length=1,
        description="Tool that produced this data",
    )


class SentimentAnalysis(BaseModel):
    """Output from the Sentiment Analyst agent (MULTI-02).

    Captures a composite sentiment score with component breakdown,
    key signals, and confidence. Constraints enforce at least one
    component and one key signal.
    """

    ticker: str = Field(
        description="Stock ticker symbol",
    )
    composite_score: float = Field(
        ge=-1.0,
        le=1.0,
        description="Weighted composite sentiment (-1 bearish to +1 bullish)",
    )
    components: list[SentimentComponent] = Field(
        min_length=1,
        description="Component breakdown of sentiment score",
    )
    key_signals: list[str] = Field(
        min_length=1,
        description="Notable sentiment signals",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence in sentiment assessment",
    )


class TechnicalIndicator(BaseModel):
    """A single computed technical indicator with tool citation.

    Every indicator must cite source_tool to prevent the LLM from
    hallucinating technical analysis (T-04-01, T-04-02).
    """

    indicator: str = Field(
        description="e.g., 'RSI', '50-day SMA', 'Volatility'",
    )
    value: str = Field(
        description="The indicator value",
    )
    interpretation: str = Field(
        description="What this means (bullish/bearish/neutral)",
    )
    source_tool: str = Field(
        min_length=1,
        description="Must be 'get_price_data'",
    )


class TechnicalAnalysis(BaseModel):
    """Output from the Technical/Quant Analyst agent (MULTI-03).

    Captures momentum and volatility assessments with computed
    indicators. Constraints enforce at least 2 indicators with
    tool citations, preventing LLM hallucination of technical data.
    """

    ticker: str = Field(
        description="Stock ticker symbol",
    )
    momentum_assessment: str = Field(
        description="Overall momentum conclusion",
    )
    volatility_assessment: str = Field(
        description="Overall volatility conclusion",
    )
    indicators: list[TechnicalIndicator] = Field(
        min_length=2,
        description="Computed technical indicators with tool citations",
    )
    bull_factors: list[str] = Field(
        min_length=1,
        description="Positive technical factors",
    )
    bear_factors: list[str] = Field(
        min_length=1,
        description="Negative technical factors",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence in technical assessment",
    )


class AnalystReport(BaseModel):
    """Wrapper for an analyst's output in the pipeline state.

    Used by LangGraph nodes to package specialist output with
    metadata (tokens consumed, any error) for the Research Manager.
    """

    analyst: Literal["fundamental", "sentiment", "technical"] = Field(
        description="Which specialist produced this report",
    )
    analysis: dict = Field(
        description="model_dump() of the specialist output",
    )
    tokens_used: int = Field(
        ge=0,
        description="Total tokens consumed by this analyst run",
    )
    error: str | None = Field(
        default=None,
        description="Error message if the analyst failed",
    )
