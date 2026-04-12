"""LangGraph pipeline module for the research pipeline.

Re-exports key components for convenient import:
    build_pipeline: Construct and compile the StateGraph.
    extract_node: LangGraph node wrapping the extraction agent (Haiku).
    analyze_node: LangGraph node wrapping the analysis agent (Sonnet).
    create_checkpointer: Sync PostgresSaver context manager.
    create_async_checkpointer: Async PostgresSaver context manager.
"""

from ai_hedge_fund.graph.checkpointer import (
    create_async_checkpointer,
    create_checkpointer,
)
from ai_hedge_fund.graph.nodes import analyze_node, extract_node
from ai_hedge_fund.graph.pipeline import build_pipeline

__all__ = [
    "analyze_node",
    "build_pipeline",
    "create_async_checkpointer",
    "create_checkpointer",
    "extract_node",
]
