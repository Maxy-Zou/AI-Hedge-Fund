"""Observability module for the AI Hedge Fund pipeline.

Re-exports key components for convenient import:
    create_langfuse_config: Build LangGraph config with Langfuse tracing.
    create_invocation_config: Full config with tracing + budget tracker.
    shutdown_langfuse: Flush pending Langfuse traces before exit.
"""

from ai_hedge_fund.observability.budget import create_invocation_config
from ai_hedge_fund.observability.langfuse import (
    create_langfuse_config,
    shutdown_langfuse,
)

__all__ = [
    "create_invocation_config",
    "create_langfuse_config",
    "shutdown_langfuse",
]
