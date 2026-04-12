"""LangGraph pipeline module for the research pipelines.

Re-exports key components for convenient import:
    build_pipeline: Phase-1 StateGraph (extract -> analyze).
    build_research_pipeline: Phase-3 StateGraph (research -> signal).
    extract_node: LangGraph node wrapping the extraction agent (Haiku).
    analyze_node: LangGraph node wrapping the analysis agent (Sonnet).
    research_node: LangGraph node wrapping the research agent (Sonnet+tools).
    signal_node: LangGraph node wrapping the signal agent (Sonnet).
    create_checkpointer: Sync PostgresSaver context manager.
    create_async_checkpointer: Async PostgresSaver context manager.
"""

from ai_hedge_fund.graph.checkpointer import (
    create_async_checkpointer,
    create_checkpointer,
)
from ai_hedge_fund.graph.nodes import (
    analyze_node,
    extract_node,
    research_node,
    signal_node,
)
from ai_hedge_fund.graph.pipeline import build_pipeline, build_research_pipeline

__all__ = [
    "analyze_node",
    "build_pipeline",
    "build_research_pipeline",
    "create_async_checkpointer",
    "create_checkpointer",
    "extract_node",
    "research_node",
    "signal_node",
]
