"""LangGraph state schemas for the research pipeline.

PipelineState is a TypedDict used as the state type for LangGraph
StateGraph. It carries data through the pipeline nodes (extraction,
analysis, debate, synthesis). Required fields must be set at graph
invocation; optional fields are populated by pipeline nodes.
"""

from __future__ import annotations

from typing import Required, TypedDict


class PipelineState(TypedDict, total=False):
    """State flowing through the LangGraph research pipeline.

    Required fields:
        ticker: Stock ticker symbol being analyzed.
        raw_text: Raw filing or document text for analysis.

    Optional fields (populated by pipeline nodes):
        extraction: Extracted data from the filing (dict from ExtractionOutput.model_dump()).
        analysis: Analysis results (dict from AnalysisOutput.model_dump()).
        error: Error message if any pipeline step failed.
    """

    ticker: Required[str]
    raw_text: Required[str]
    extraction: dict | None
    analysis: dict | None
    error: str | None
