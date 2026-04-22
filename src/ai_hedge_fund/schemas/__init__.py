"""Schema definitions for LangGraph state and PydanticAI agent outputs."""

from __future__ import annotations

from ai_hedge_fund.schemas.agents import (
    AnalysisOutput,
    AnalystReport,
    ExtractionOutput,
    FilingCitation,
    FundamentalAnalysis,
    SentimentAnalysis,
    SentimentComponent,
    SignalOutput,
    TechnicalAnalysis,
    TechnicalIndicator,
    ThesisOutput,
    ThesisPoint,
    ValuationMetric,
)
from ai_hedge_fund.schemas.debate import (
    BearCase,
    BearClaim,
    BullCase,
    BullClaim,
    DebateSynthesis,
    FinalArguments,
    RebuttalAct,
    RebuttalPoint,
)
from ai_hedge_fund.schemas.state import (
    MultiAgentPipelineState,
    PipelineState,
    ResearchPipelineState,
)

__all__ = [
    "AnalysisOutput",
    "AnalystReport",
    "BearCase",
    "BearClaim",
    "BullCase",
    "BullClaim",
    "DebateSynthesis",
    "ExtractionOutput",
    "FilingCitation",
    "FinalArguments",
    "FundamentalAnalysis",
    "MultiAgentPipelineState",
    "PipelineState",
    "RebuttalAct",
    "RebuttalPoint",
    "ResearchPipelineState",
    "SentimentAnalysis",
    "SentimentComponent",
    "SignalOutput",
    "TechnicalAnalysis",
    "TechnicalIndicator",
    "ThesisOutput",
    "ThesisPoint",
    "ValuationMetric",
]
