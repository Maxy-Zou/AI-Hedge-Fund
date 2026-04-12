"""Pipeline budget enforcement integration with Langfuse tracing.

Bundles a Langfuse-traced invocation config with a fresh
PipelineBudgetTracker for complete pipeline run setup.
"""

from __future__ import annotations

from ai_hedge_fund.agents.base import PipelineBudgetTracker
from ai_hedge_fund.config import get_settings
from ai_hedge_fund.observability.langfuse import create_langfuse_config


def create_invocation_config(
    thread_id: str,
    ticker: str,
    session_id: str | None = None,
    tags: list[str] | None = None,
) -> tuple[dict, PipelineBudgetTracker]:
    """Create a complete invocation config with Langfuse tracing and budget tracker.

    Combines Langfuse observability config with a fresh PipelineBudgetTracker
    initialized from application settings. Returns both as a tuple.

    Usage::

        config, tracker = create_invocation_config("run-AAPL-001", "AAPL")
        result = await graph.ainvoke(state, config)
        # After run, update tracker with actual usage from result

    Args:
        thread_id: Unique identifier for this graph invocation thread.
        ticker: Stock ticker being analyzed (added as a tag).
        session_id: Optional Langfuse session ID (defaults to thread_id).
        tags: Optional additional tags for Langfuse trace filtering.

    Returns:
        Tuple of (config_dict, budget_tracker) for graph invocation.
    """
    settings = get_settings()
    all_tags = [f"ticker:{ticker}"] + (tags or [])

    config = create_langfuse_config(
        thread_id=thread_id,
        session_id=session_id,
        tags=all_tags,
    )

    tracker = PipelineBudgetTracker(total_limit=settings.pipeline_total_token_limit)

    return config, tracker
