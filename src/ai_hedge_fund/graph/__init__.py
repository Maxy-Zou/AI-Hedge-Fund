"""LangGraph pipeline module for the research pipelines.

Re-exports key components for convenient import:
    build_pipeline: Phase-1 StateGraph (extract -> analyze).
    build_research_pipeline: Phase-3 StateGraph (research -> signal).
    build_multi_agent_pipeline: Phase-4 StateGraph (parallel analysts
        -> manager -> signal).
    build_debate_pipeline: Phase-5 StateGraph (parallel analysts ->
        manager -> bull -> bear -> rebuttal -> final_arguments ->
        debate_synthesis -> signal). Added alongside (not replacing)
        build_multi_agent_pipeline -- Option B per 05-RESEARCH.md.
    extract_node: LangGraph node wrapping the extraction agent (Haiku).
    analyze_node: LangGraph node wrapping the analysis agent (Sonnet).
    research_node: LangGraph node wrapping the research agent (Sonnet+tools).
    signal_node: LangGraph node wrapping the signal agent (Sonnet).
    fundamental_node / sentiment_node / technical_node: Phase-4 parallel
        analyst nodes.
    manager_node: Phase-4 research-manager synthesis node (Opus).
    multi_agent_signal_node: Phase-4 signal adapter that consumes
        MultiAgentPipelineState instead of ResearchPipelineState.
    bull_node / bear_node / rebuttal_node / final_arguments_node /
        debate_synthesis_node: Phase-5 5-act debate nodes.
        debate_synthesis_node overwrites state['thesis'] with the
        post-debate revised_thesis so the signal adapter consumes the
        debated version unchanged.
    create_checkpointer: Sync PostgresSaver context manager.
    create_async_checkpointer: Async PostgresSaver context manager.
"""

from ai_hedge_fund.graph.checkpointer import (
    create_async_checkpointer,
    create_checkpointer,
)
from ai_hedge_fund.graph.nodes import (
    analyze_node,
    bear_node,
    bull_node,
    debate_synthesis_node,
    extract_node,
    final_arguments_node,
    fundamental_node,
    manager_node,
    multi_agent_signal_node,
    rebuttal_node,
    research_node,
    risk_manager_node,
    route_after_risk,
    sentiment_node,
    signal_node,
    technical_node,
)
from ai_hedge_fund.graph.pipeline import (
    build_debate_pipeline,
    build_multi_agent_pipeline,
    build_pipeline,
    build_research_pipeline,
)
from ai_hedge_fund.graph.risk_deps import RiskDeps

__all__ = [
    "RiskDeps",
    "analyze_node",
    "bear_node",
    "build_debate_pipeline",
    "build_multi_agent_pipeline",
    "build_pipeline",
    "build_research_pipeline",
    "bull_node",
    "create_async_checkpointer",
    "create_checkpointer",
    "debate_synthesis_node",
    "extract_node",
    "final_arguments_node",
    "fundamental_node",
    "manager_node",
    "multi_agent_signal_node",
    "rebuttal_node",
    "research_node",
    "risk_manager_node",
    "route_after_risk",
    "sentiment_node",
    "signal_node",
    "technical_node",
]
