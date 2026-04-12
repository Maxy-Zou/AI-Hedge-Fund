"""Langfuse observability integration for the research pipeline.

Provides CallbackHandler factory for LangGraph invocations and
shutdown helper for flushing pending traces.

Threat model T-03-01: Langfuse credentials loaded from environment
(never hardcoded). Graceful degradation when not configured -- pipeline
runs without tracing rather than failing.
"""

from __future__ import annotations

import structlog
from langfuse import get_client
from langfuse.langchain import CallbackHandler

from ai_hedge_fund.config import get_settings

logger = structlog.get_logger(__name__)


def create_langfuse_handler() -> CallbackHandler | None:
    """Create a Langfuse CallbackHandler if credentials are configured.

    Returns None if LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY are not set,
    allowing the pipeline to run without tracing (graceful degradation).

    Returns:
        CallbackHandler for LangGraph tracing, or None if not configured.
    """
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.info("langfuse_not_configured", msg="Skipping Langfuse -- no credentials in env")
        return None
    return CallbackHandler()


def create_langfuse_config(
    thread_id: str,
    session_id: str | None = None,
    tags: list[str] | None = None,
    user_id: str = "pipeline-v1",
) -> dict:
    """Create a LangGraph invocation config with Langfuse tracing.

    Returns a config dict with a configurable thread_id and optional
    Langfuse callbacks. If Langfuse is not configured, returns config
    without callbacks (pipeline still runs normally).

    Args:
        thread_id: Unique identifier for this graph invocation thread.
        session_id: Optional Langfuse session ID (defaults to thread_id).
        tags: Optional list of tags for Langfuse trace filtering.
        user_id: User identifier for Langfuse traces.

    Returns:
        Dict suitable for passing to graph.ainvoke(state, config).
    """
    config: dict = {
        "configurable": {"thread_id": thread_id},
    }

    handler = create_langfuse_handler()
    if handler:
        config["callbacks"] = [handler]
        config["metadata"] = {
            "langfuse_session_id": session_id or thread_id,
            "langfuse_user_id": user_id,
            "langfuse_tags": tags or [],
        }

    return config


def shutdown_langfuse() -> None:
    """Flush pending Langfuse traces. Call before process exit.

    Safe to call even when Langfuse is not configured -- catches and
    logs any errors without propagating.
    """
    try:
        get_client().flush()
    except Exception:
        logger.warning("langfuse_flush_failed", msg="Could not flush Langfuse traces")
