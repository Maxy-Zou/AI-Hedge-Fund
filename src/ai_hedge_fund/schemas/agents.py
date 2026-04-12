"""PydanticAI output schemas for agent responses.

Each schema defines the typed, validated output for a specific agent type.
Pydantic Field constraints enforce data quality at the validation boundary:
- min_length prevents empty lists
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


class ThesisOutput(BaseModel):
    """Output from thesis synthesis (Opus tier).

    Captures the structured investment thesis from the adversarial
    bull/bear debate, including both sides, confidence, and risk factors.
    """

    ticker: str = Field(
        description="Stock ticker symbol",
    )
    bull_case: list[str] = Field(
        min_length=1,
        description="Bull case arguments with evidence citations",
    )
    bear_case: list[str] = Field(
        min_length=1,
        description="Bear case arguments with evidence citations",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence score 0-100 in the thesis direction",
    )
    risk_factors: list[str] = Field(
        min_length=1,
        description="Named risk factors that could invalidate the thesis",
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
