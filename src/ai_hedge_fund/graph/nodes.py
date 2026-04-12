"""LangGraph node functions wrapping PydanticAI agents.

Each node function wraps a PydanticAI agent call and returns a NEW dict
(immutable pattern -- never mutates the state parameter in place).
UsageLimits are enforced on every agent.run() call per threat model T-03-02.

Nodes:
    extract_node: Wraps extraction_agent (Haiku) for financial data extraction.
    analyze_node: Wraps analysis_agent (Sonnet) for financial analysis.
"""

from __future__ import annotations

import structlog
from pydantic_ai.exceptions import UsageLimitExceeded

from ai_hedge_fund.agents.analysis import analysis_agent, get_analysis_limits
from ai_hedge_fund.agents.extraction import extraction_agent, get_extraction_limits
from ai_hedge_fund.schemas.state import PipelineState

logger = structlog.get_logger(__name__)


async def extract_node(state: PipelineState) -> dict:
    """Wrap extraction agent as LangGraph node.

    Runs the Haiku extraction agent with UsageLimits budget enforcement.
    Returns a NEW dict with extraction results (immutable pattern per
    threat model T-03-03). On budget exceeded, returns error in state.

    Args:
        state: Current pipeline state with ticker and raw_text.

    Returns:
        Dict with extraction results or error message.
    """
    try:
        limits = get_extraction_limits()
        result = await extraction_agent.run(
            f"Extract key financial metrics from: {state['raw_text']}",
            usage_limits=limits,
        )
        usage = result.usage()
        logger.info(
            "extraction_complete",
            ticker=state["ticker"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"extraction": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error("extraction_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Extraction budget exceeded: {e}"}


async def analyze_node(state: PipelineState) -> dict:
    """Wrap analysis agent as LangGraph node.

    Runs the Sonnet analysis agent with UsageLimits budget enforcement.
    Skips execution if a prior node set an error. Returns a NEW dict
    with analysis results (immutable pattern per threat model T-03-03).

    Args:
        state: Current pipeline state with ticker and extraction data.

    Returns:
        Dict with analysis results, error message, or empty dict if skipped.
    """
    if state.get("error"):
        return {}  # Skip if prior node errored

    try:
        limits = get_analysis_limits()
        result = await analysis_agent.run(
            f"Analyze financial data for {state['ticker']}: {state['extraction']}",
            usage_limits=limits,
        )
        usage = result.usage()
        logger.info(
            "analysis_complete",
            ticker=state["ticker"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"analysis": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error("analysis_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Analysis budget exceeded: {e}"}
