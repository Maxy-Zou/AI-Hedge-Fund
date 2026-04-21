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
    fundamental_node / sentiment_node / technical_node: Phase-4 parallel
        analyst nodes. Each returns a single-element list under
        ``analyst_reports`` so the ``operator.add`` reducer on
        ``MultiAgentPipelineState`` merges the three reports into one list.
    manager_node: Phase-4 fan-in synthesis node. Reads the accumulated
        analyst_reports, formats them for the manager agent, and produces
        a ThesisOutput dict.
    multi_agent_signal_node: Phase-4 signal adapter that consumes
        ``MultiAgentPipelineState`` (same thesis/signal/error keys as the
        Phase-3 state) and calls the existing signal_agent.
"""

from __future__ import annotations

from datetime import date

import structlog
from pydantic_ai.exceptions import UsageLimitExceeded

from ai_hedge_fund.agents.analysis import analysis_agent, get_analysis_limits
from ai_hedge_fund.agents.extraction import extraction_agent, get_extraction_limits
from ai_hedge_fund.agents.fundamental import fundamental_agent, get_fundamental_limits
from ai_hedge_fund.agents.manager import (
    format_analyst_reports,
    get_manager_limits,
    manager_agent,
)
from ai_hedge_fund.agents.research import (
    ResearchDeps,
    get_research_limits,
    research_agent,
)
from ai_hedge_fund.agents.sentiment import get_sentiment_limits, sentiment_agent
from ai_hedge_fund.agents.signal import get_signal_limits, signal_agent
from ai_hedge_fund.agents.technical import get_technical_limits, technical_agent
from ai_hedge_fund.schemas.state import (
    MultiAgentPipelineState,
    PipelineState,
    ResearchPipelineState,
)

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


# ---------------------------------------------------------------------------
# Phase 4 multi-agent nodes: parallel analysts + research manager + signal.
# ---------------------------------------------------------------------------


async def fundamental_node(state: MultiAgentPipelineState) -> dict:
    """Wrap the fundamental analyst agent as a LangGraph node.

    Builds ``ResearchDeps`` from ``state["ticker"]`` and the parsed
    ``as_of_date`` and runs the fundamental_agent under an ANALYSIS-tier
    UsageLimits cap (T-04-04, T-04-07). Returns a NEW dict wrapping the
    analyst output in a single-element ``analyst_reports`` list so the
    ``operator.add`` reducer on ``MultiAgentPipelineState`` concatenates
    it with the other analysts' outputs.

    On UsageLimitExceeded, the error is propagated into the analyst_reports
    list (not raised) so the pipeline can continue to the manager; failed
    analysts surface as ``{"analyst": "fundamental", "error": "..."}``.

    Args:
        state: Multi-agent pipeline state with required ``ticker`` and
            ``as_of_date``.

    Returns:
        Dict with a single-element ``analyst_reports`` list containing
        either the analyst output (on success) or an error entry.
    """
    try:
        deps = ResearchDeps(
            ticker=state["ticker"],
            as_of_date=date.fromisoformat(state["as_of_date"]),
        )
        limits = get_fundamental_limits()
        result = await fundamental_agent.run(
            f"Produce a fundamental analysis for {deps.ticker}",
            deps=deps,
            usage_limits=limits,
        )
        usage = result.usage()
        logger.info(
            "fundamental_complete",
            ticker=deps.ticker,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {
            "analyst_reports": [
                {
                    "analyst": "fundamental",
                    "analysis": result.output.model_dump(),
                    "tokens_used": usage.total_tokens,
                }
            ]
        }
    except UsageLimitExceeded as e:
        logger.error("fundamental_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {
            "analyst_reports": [
                {
                    "analyst": "fundamental",
                    "error": f"Fundamental budget exceeded: {e}",
                }
            ]
        }


async def sentiment_node(state: MultiAgentPipelineState) -> dict:
    """Wrap the sentiment analyst agent as a LangGraph node.

    Same pattern as ``fundamental_node``: runs sentiment_agent under an
    ANALYSIS-tier budget cap and returns a single-element
    ``analyst_reports`` list for the ``operator.add`` reducer. Analyst
    errors propagate as error entries in the list so the manager can still
    synthesize whatever analysts did succeed.

    Args:
        state: Multi-agent pipeline state with required ``ticker`` and
            ``as_of_date``.

    Returns:
        Dict with a single-element ``analyst_reports`` list.
    """
    try:
        deps = ResearchDeps(
            ticker=state["ticker"],
            as_of_date=date.fromisoformat(state["as_of_date"]),
        )
        limits = get_sentiment_limits()
        result = await sentiment_agent.run(
            f"Produce a sentiment analysis for {deps.ticker}",
            deps=deps,
            usage_limits=limits,
        )
        usage = result.usage()
        logger.info(
            "sentiment_complete",
            ticker=deps.ticker,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {
            "analyst_reports": [
                {
                    "analyst": "sentiment",
                    "analysis": result.output.model_dump(),
                    "tokens_used": usage.total_tokens,
                }
            ]
        }
    except UsageLimitExceeded as e:
        logger.error("sentiment_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {
            "analyst_reports": [
                {
                    "analyst": "sentiment",
                    "error": f"Sentiment budget exceeded: {e}",
                }
            ]
        }


async def technical_node(state: MultiAgentPipelineState) -> dict:
    """Wrap the technical/quant analyst agent as a LangGraph node.

    Same pattern as ``fundamental_node`` and ``sentiment_node``. Runs
    technical_agent under an ANALYSIS-tier budget cap and returns a
    single-element ``analyst_reports`` list for the ``operator.add``
    reducer.

    Args:
        state: Multi-agent pipeline state with required ``ticker`` and
            ``as_of_date``.

    Returns:
        Dict with a single-element ``analyst_reports`` list.
    """
    try:
        deps = ResearchDeps(
            ticker=state["ticker"],
            as_of_date=date.fromisoformat(state["as_of_date"]),
        )
        limits = get_technical_limits()
        result = await technical_agent.run(
            f"Produce a technical and momentum analysis for {deps.ticker}",
            deps=deps,
            usage_limits=limits,
        )
        usage = result.usage()
        logger.info(
            "technical_complete",
            ticker=deps.ticker,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {
            "analyst_reports": [
                {
                    "analyst": "technical",
                    "analysis": result.output.model_dump(),
                    "tokens_used": usage.total_tokens,
                }
            ]
        }
    except UsageLimitExceeded as e:
        logger.error("technical_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {
            "analyst_reports": [
                {
                    "analyst": "technical",
                    "error": f"Technical budget exceeded: {e}",
                }
            ]
        }


async def manager_node(state: MultiAgentPipelineState) -> dict:
    """Wrap the research-manager synthesis agent as a LangGraph node.

    Reads the accumulated ``analyst_reports`` from state (already merged by
    the ``operator.add`` reducer across the three parallel analysts),
    formats them via ``format_analyst_reports``, and runs manager_agent
    under the REASONING-tier (Opus) budget cap. Returns a NEW dict with
    the synthesized thesis or an error message.

    Args:
        state: Multi-agent pipeline state with at least ``ticker`` and
            ``as_of_date``; ``analyst_reports`` is expected after fan-in.

    Returns:
        Dict with ``thesis`` on success or ``error`` when there are no
        analyst reports to synthesize or the budget is exceeded.
    """
    reports = state.get("analyst_reports", [])
    if not reports:
        logger.error("manager_no_reports", ticker=state.get("ticker"))
        return {"error": "No analyst reports available for synthesis"}

    reports_text = format_analyst_reports(reports)
    prompt = (
        f"Synthesize these analyst reports for {state['ticker']} as of "
        f"{state['as_of_date']}:\n\n{reports_text}"
    )

    try:
        limits = get_manager_limits()
        result = await manager_agent.run(prompt, usage_limits=limits)
        usage = result.usage()
        logger.info(
            "manager_complete",
            ticker=state["ticker"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"thesis": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error("manager_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Manager budget exceeded: {e}"}


async def multi_agent_signal_node(state: MultiAgentPipelineState) -> dict:
    """Phase-4 signal node accepting ``MultiAgentPipelineState``.

    Thin adapter around the existing signal_agent -- the Phase-4 state
    carries the same ``thesis``/``signal``/``error`` keys as
    ``ResearchPipelineState``, so the underlying logic is identical:
      - Short-circuit with ``{}`` if a prior node already set ``error``.
      - Return an explicit error if no thesis is available.
      - Otherwise run signal_agent and return the serialized signal.

    Kept separate from ``signal_node`` so each node's state type is
    unambiguous to LangGraph and to future static analysis.

    Args:
        state: Multi-agent pipeline state with optional ``thesis`` dict.

    Returns:
        Dict with ``signal`` on success, ``error`` on budget or missing
        thesis, or empty dict when skipped due to upstream error.
    """
    if state.get("error"):
        return {}  # Skip: preserve upstream error without overwriting.
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
            "multi_agent_signal_complete",
            ticker=state["ticker"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"signal": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error(
            "multi_agent_signal_budget_exceeded",
            ticker=state["ticker"],
            error=str(e),
        )
        return {"error": f"Signal budget exceeded: {e}"}
