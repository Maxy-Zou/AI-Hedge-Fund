"""LangGraph pipeline module for the research pipelines.

Re-exports key components for convenient import:
    build_pipeline: Phase-1 StateGraph (extract -> analyze).
    build_research_pipeline: Phase-3 StateGraph (research -> signal).
    build_multi_agent_pipeline: Phase-4 StateGraph (parallel analysts
        -> manager -> signal).
    extract_node: LangGraph node wrapping the extraction agent (Haiku).
    analyze_node: LangGraph node wrapping the analysis agent (Sonnet).
    research_node: LangGraph node wrapping the research agent (Sonnet+tools).
    signal_node: LangGraph node wrapping the signal agent (Sonnet).
    fundamental_node / sentiment_node / technical_node: Phase-4 parallel
        analyst nodes.
    manager_node: Phase-4 research-manager synthesis node (Opus).
    multi_agent_signal_node: Phase-4 signal adapter that consumes
        MultiAgentPipelineState instead of ResearchPipelineState.
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
    fundamental_node,
    manager_node,
    multi_agent_signal_node,
    research_node,
    sentiment_node,
    signal_node,
    technical_node,
)
from ai_hedge_fund.graph.pipeline import (
    build_multi_agent_pipeline,
    build_pipeline,
    build_research_pipeline,
)

__all__ = [
    "analyze_node",
    "build_multi_agent_pipeline",
    "build_pipeline",
    "build_research_pipeline",
    "create_async_checkpointer",
    "create_checkpointer",
    "extract_node",
    "fundamental_node",
    "manager_node",
    "multi_agent_signal_node",
    "research_node",
    "sentiment_node",
    "signal_node",
    "technical_node",
]
