"""LangGraph node functions wrapping PydanticAI agents.

Each node function wraps a PydanticAI agent call and returns a NEW dict
(immutable pattern -- never mutates the state parameter in place).
UsageLimits are enforced on every agent.run() call per threat model T-03-02
and T-03-06/07 (DoS via budget exhaustion).

Nodes:
    extract_node: Wraps extraction_agent (Haiku) for financial data extraction.
    analyze_node: Wraps analysis_agent (Sonnet) for financial analysis.
    research_node: Wraps research_agent (Sonnet, tool-augmented) and
        produces a ThesisOutput dict on ResearchPipelineState.
    signal_node: Wraps signal_agent (Sonnet) converting a thesis dict to
        a SignalOutput dict; short-circuits on upstream error / missing thesis.
"""

from __future__ import annotations

from datetime import date

import structlog
from pydantic_ai.exceptions import UsageLimitExceeded

from ai_hedge_fund.agents.analysis import analysis_agent, get_analysis_limits
from ai_hedge_fund.agents.extraction import extraction_agent, get_extraction_limits
from ai_hedge_fund.agents.research import (
    ResearchDeps,
    get_research_limits,
    research_agent,
)
from ai_hedge_fund.agents.signal import get_signal_limits, signal_agent
from ai_hedge_fund.schemas.state import PipelineState, ResearchPipelineState

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


async def research_node(state: ResearchPipelineState) -> dict:
    """Wrap research agent as LangGraph node.

    Builds ResearchDeps from the pipeline state (ticker + parsed as_of_date)
    and runs the tool-augmented research agent under a Sonnet-tier
    UsageLimits cap (T-03-06 DoS mitigation). Returns a NEW dict carrying
    the thesis ``model_dump()`` or an error message; the existing state
    parameter is never mutated (T-03-08 tampering mitigation).

    Args:
        state: Research pipeline state with required ``ticker`` and
            ``as_of_date`` (ISO-format string).

    Returns:
        Dict with ``thesis`` on success or ``error`` on budget exceedance.
    """
    try:
        deps = ResearchDeps(
            ticker=state["ticker"],
            as_of_date=date.fromisoformat(state["as_of_date"]),
        )
        limits = get_research_limits()
        result = await research_agent.run(
            f"Produce a comprehensive investment thesis for {deps.ticker}",
            deps=deps,
            usage_limits=limits,
        )
        usage = result.usage()
        logger.info(
            "research_complete",
            ticker=deps.ticker,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"thesis": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error("research_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Research budget exceeded: {e}"}


async def signal_node(state: ResearchPipelineState) -> dict:
    """Wrap signal agent as LangGraph node.

    Takes the thesis dict from state and asks the signal agent to derive a
    trade signal. Short-circuits in two cases:
      - Upstream error already set on state -> return {} (don't overwrite).
      - Thesis missing or None -> return an explicit error dict so the
        pipeline surfaces the upstream gap rather than silently producing
        a signal from nothing.

    Args:
        state: Research pipeline state with optional ``thesis`` dict.

    Returns:
        Dict with ``signal`` on success, ``error`` on budget or missing
        thesis, or empty dict when skipped due to upstream error.
    """
    if state.get("error"):
        return {}  # Skip if prior node errored -- do not overwrite error.
    thesis = state.get("thesis")
    if thesis is None:
        return {"error": "No thesis available for signal generation"}
    try:
        limits = get_signal_limits()
        result = await signal_agent.run(
            f"Generate a trade signal for {state['ticker']} based on this thesis:\n{thesis}",
            usage_limits=limits,
        )
        usage = result.usage()
        logger.info(
            "signal_complete",
            ticker=state["ticker"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"signal": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error("signal_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Signal budget exceeded: {e}"}
