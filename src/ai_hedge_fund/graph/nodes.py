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
    bull_node / bear_node / rebuttal_node / final_arguments_node /
        debate_synthesis_node: Phase-5 5-act debate nodes. Sequential chain
        producing BullCase -> BearCase -> RebuttalAct -> FinalArguments ->
        DebateSynthesis. ``debate_synthesis_node`` OVERWRITES the LLM-
        produced ``quality_score`` with ``compute_quality_score()`` (tool-
        first per CLAUDE.md) and overwrites ``pre_debate_confidence`` with
        ``state['thesis']['confidence']`` read BEFORE the agent runs
        (Pitfall-3 mitigation). Returns BOTH ``debate_synthesis`` AND
        ``thesis`` keys so the downstream signal node consumes the debated
        thesis without code changes.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import structlog
from langgraph.types import interrupt  # Phase 8: HITL pause primitive
from pydantic_ai.exceptions import UsageLimitExceeded

from ai_hedge_fund.agents.analysis import analysis_agent, get_analysis_limits
from ai_hedge_fund.agents.bear import (
    bear_agent,
    format_bull_case_for_bear,
    get_bear_limits,
)
from ai_hedge_fund.agents.bull import (
    bull_agent,
    format_analyst_evidence,
    get_bull_limits,
)
from ai_hedge_fund.agents.debate_synthesis import (
    compute_quality_score,
    debate_synthesis_agent,
    format_debate_for_synthesis,
    get_debate_synthesis_limits,
)
from ai_hedge_fund.agents.extraction import extraction_agent, get_extraction_limits
from ai_hedge_fund.agents.final_arguments import (
    final_arguments_agent,
    format_debate_for_final,
    get_final_arguments_limits,
)
from ai_hedge_fund.agents.fundamental import fundamental_agent, get_fundamental_limits
from ai_hedge_fund.agents.manager import (
    format_analyst_reports,
    get_manager_limits,
    manager_agent,
)
from ai_hedge_fund.agents.rebuttal import (
    format_debate_for_rebuttal,
    get_rebuttal_limits,
    rebuttal_agent,
)
from ai_hedge_fund.agents.research import (
    ResearchDeps,
    get_research_limits,
    research_agent,
)
from ai_hedge_fund.agents.risk_manager import (
    format_risk_context_for_rationale,
    get_risk_manager_limits,
    risk_manager_agent,
)
from ai_hedge_fund.agents.sentiment import get_sentiment_limits, sentiment_agent
from ai_hedge_fund.agents.signal import get_signal_limits, signal_agent
from ai_hedge_fund.agents.technical import get_technical_limits, technical_agent
from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.graph.memory_deps import MemoryDeps
from ai_hedge_fund.graph.review_deps import ReviewDeps
from ai_hedge_fund.graph.risk_deps import RiskDeps
from ai_hedge_fund.memory.beliefs import (
    belief_path_for_sector,
    belief_path_for_ticker,
    load_belief,
)
from ai_hedge_fund.memory.episodic import _normalise_as_of
from ai_hedge_fund.memory.recall import query_episodic
from ai_hedge_fund.output.signal import assemble_final_signal
from ai_hedge_fund.review.decision import ReviewDecision
from ai_hedge_fund.review.policy import ReviewPolicy, compute_review_policy_sha
from ai_hedge_fund.risk.checks import (
    check_exclusions,
    check_position_size,
    check_sector_concentration,
)
from ai_hedge_fund.risk.correlation import check_correlation
from ai_hedge_fund.risk.drawdown import check_drawdown
from ai_hedge_fund.risk.policy import compute_policy_sha, load_policy
from ai_hedge_fund.risk.portfolio import load_portfolio
from ai_hedge_fund.risk.sizing import derive_candidate_size_pct
from ai_hedge_fund.schemas.risk import CheckResult, RiskAssessment, Violation
from ai_hedge_fund.schemas.state import (
    DebatePipelineState,
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
        usage = result.usage
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
        usage = result.usage
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
        usage = result.usage
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
        usage = result.usage
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
        usage = result.usage
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
        usage = result.usage
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
        usage = result.usage
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
        usage = result.usage
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
        usage = result.usage
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


# ---------------------------------------------------------------------------
# Phase 5 debate nodes: bull -> bear -> rebuttal -> final_arguments ->
# debate_synthesis. Each follows the manager_node template: short-circuit on
# upstream error, run zero-tool REASONING-tier agent under UsageLimits, catch
# UsageLimitExceeded and propagate into state['error']. debate_synthesis_node
# additionally overwrites two LLM-authored fields with pipeline-authoritative
# values (compute_quality_score output + pre_debate_confidence from state).
# ---------------------------------------------------------------------------


async def bull_node(state: DebatePipelineState) -> dict:
    """Phase-5 Bull Advocate node -- produces BullCase from thesis + analyst reports.

    Short-circuits on upstream error. Requires ``state['thesis']`` to exist
    (written by manager_node). Does not call any external tool -- bull_agent
    is zero-tools and reads evidence from state via
    ``format_analyst_evidence``.

    Args:
        state: DebatePipelineState carrying ``analyst_reports`` and ``thesis``.

    Returns:
        Dict with ``bull_case`` on success, ``error`` when budget exceeded or
        precondition missing, or empty dict when skipped due to upstream error.
    """
    if state.get("error"):
        return {}
    thesis = state.get("thesis")
    if thesis is None:
        logger.error("bull_no_thesis", ticker=state.get("ticker"))
        return {"error": "No thesis available for bull debate"}
    reports = state.get("analyst_reports", [])
    prompt = format_analyst_evidence(reports, thesis)
    try:
        limits = get_bull_limits()
        result = await bull_agent.run(prompt, usage_limits=limits)
        usage = result.usage
        logger.info(
            "bull_complete",
            ticker=state["ticker"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"bull_case": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error("bull_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Bull budget exceeded: {e}"}


async def bear_node(state: DebatePipelineState) -> dict:
    """Phase-5 Bear Advocate node -- produces BearCase that rebuts bull claims.

    Short-circuits on upstream error. Requires ``state['thesis']`` AND
    ``state['bull_case']`` -- the bear agent must see what it is rebutting.
    Builds the prompt by concatenating ``format_analyst_evidence(reports,
    thesis)`` and ``format_bull_case_for_bear(bull_case)`` with a
    ``"\\n\\n---\\n\\n"`` separator.

    Args:
        state: DebatePipelineState carrying ``analyst_reports``, ``thesis``,
            and ``bull_case``.

    Returns:
        Dict with ``bear_case`` on success, ``error`` when budget exceeded or
        precondition missing, or empty dict when skipped due to upstream error.
    """
    if state.get("error"):
        return {}
    bull_case = state.get("bull_case")
    if bull_case is None:
        logger.error("bear_no_bull_case", ticker=state.get("ticker"))
        return {"error": "No bull case available for bear debate"}
    thesis = state.get("thesis")
    reports = state.get("analyst_reports", [])
    evidence_section = format_analyst_evidence(reports, thesis)
    bull_section = format_bull_case_for_bear(bull_case)
    prompt = f"{evidence_section}\n\n---\n\n{bull_section}"
    try:
        limits = get_bear_limits()
        result = await bear_agent.run(prompt, usage_limits=limits)
        usage = result.usage
        logger.info(
            "bear_complete",
            ticker=state["ticker"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"bear_case": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error("bear_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Bear budget exceeded: {e}"}


async def rebuttal_node(state: DebatePipelineState) -> dict:
    """Phase-5 Rebuttal node -- Act 3 of the 5-act debate.

    Short-circuits on upstream error. Requires both ``state['bull_case']``
    and ``state['bear_case']``. Runs ``rebuttal_agent`` with
    ``format_debate_for_rebuttal(bull_case, bear_case)`` as the prompt under
    the REASONING-tier ``output_override=8_000`` cap (Pitfall-6 cost
    guardrail).

    Args:
        state: DebatePipelineState carrying ``bull_case`` and ``bear_case``.

    Returns:
        Dict with ``rebuttal`` on success, ``error`` when budget exceeded or
        precondition missing, or empty dict when skipped due to upstream error.
    """
    if state.get("error"):
        return {}
    bull_case = state.get("bull_case")
    bear_case = state.get("bear_case")
    if bull_case is None or bear_case is None:
        logger.error(
            "rebuttal_missing_prereq",
            ticker=state.get("ticker"),
            has_bull=bull_case is not None,
            has_bear=bear_case is not None,
        )
        return {"error": "No bull/bear case available for rebuttal"}
    prompt = format_debate_for_rebuttal(bull_case, bear_case)
    try:
        limits = get_rebuttal_limits()
        result = await rebuttal_agent.run(prompt, usage_limits=limits)
        usage = result.usage
        logger.info(
            "rebuttal_complete",
            ticker=state["ticker"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"rebuttal": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error("rebuttal_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Rebuttal budget exceeded: {e}"}


async def final_arguments_node(state: DebatePipelineState) -> dict:
    """Phase-5 Final Arguments node -- Act 4 of the 5-act debate.

    Short-circuits on upstream error. Requires ``state['bull_case']``,
    ``state['bear_case']``, AND ``state['rebuttal']`` -- closings reflect
    what survived the rebuttal. Runs ``final_arguments_agent`` under the
    REASONING-tier ``output_override=8_000`` cap.

    Args:
        state: DebatePipelineState carrying ``bull_case``, ``bear_case``,
            and ``rebuttal``.

    Returns:
        Dict with ``final_arguments`` on success, ``error`` when budget
        exceeded or precondition missing, or empty dict when skipped due
        to upstream error.
    """
    if state.get("error"):
        return {}
    rebuttal = state.get("rebuttal")
    bull_case = state.get("bull_case")
    bear_case = state.get("bear_case")
    if rebuttal is None or bull_case is None or bear_case is None:
        logger.error(
            "final_arguments_missing_prereq",
            ticker=state.get("ticker"),
            has_bull=bull_case is not None,
            has_bear=bear_case is not None,
            has_rebuttal=rebuttal is not None,
        )
        return {"error": "No rebuttal/bull/bear available for final arguments"}
    prompt = format_debate_for_final(bull_case, bear_case, rebuttal)
    try:
        limits = get_final_arguments_limits()
        result = await final_arguments_agent.run(prompt, usage_limits=limits)
        usage = result.usage
        logger.info(
            "final_arguments_complete",
            ticker=state["ticker"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"final_arguments": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error(
            "final_arguments_budget_exceeded",
            ticker=state["ticker"],
            error=str(e),
        )
        return {"error": f"Final arguments budget exceeded: {e}"}


async def debate_synthesis_node(state: DebatePipelineState) -> dict:
    """Phase-5 Debate Synthesis node -- Act 5 + tool-first quality-score enforcement.

    Reads ``pre_debate_confidence`` from ``state['thesis']['confidence']``
    BEFORE running the agent (Pitfall-3 / T-05-18 mitigation -- do not trust
    the LLM to remember this). Runs ``debate_synthesis_agent``, then:

    1. Overwrites the LLM-produced ``quality_score`` with the output of
       ``compute_quality_score(evidence_strength, logical_consistency,
       risk_coverage)`` per CLAUDE.md's "LLMs NEVER compute financial ratios"
       rule (DEBATE-04 / T-05-17 mitigation).
    2. Overwrites ``pre_debate_confidence`` with the authoritative value
       read from state before the agent ran.
    3. Returns BOTH ``debate_synthesis`` (for observability / Langfuse) AND
       ``thesis`` keys; ``thesis`` is replaced with
       ``synthesis.revised_thesis.model_dump()`` so the downstream
       ``multi_agent_signal_node`` consumes the post-debate thesis
       without any code changes (RESEARCH.md Q3 resolution).

    Immutable update via ``model_copy(update={...})`` -- never mutate the
    agent's output object in place.

    Args:
        state: DebatePipelineState carrying ``thesis``, ``bull_case``,
            ``bear_case``, ``rebuttal``, and ``final_arguments``.

    Returns:
        Dict with ``debate_synthesis`` and ``thesis`` on success, ``error``
        when budget exceeded, thesis missing/malformed, or required upstream
        act missing, or empty dict when skipped due to upstream error.

    Preconditions (WR-03):
        - ``state['thesis']`` is non-None.
        - ``state['thesis']['confidence']`` is non-None. Silently defaulting
          to 0 would distort DEBATE-04 success-criterion-4 (post - pre
          delta) with a fabricated zero baseline.
        - ``state['final_arguments']`` is non-None.
    """
    if state.get("error"):
        return {}
    thesis = state.get("thesis")
    if thesis is None:
        logger.error("debate_synthesis_no_thesis", ticker=state.get("ticker"))
        return {"error": "No thesis available for synthesis"}
    if state.get("final_arguments") is None:
        logger.error("debate_synthesis_no_final", ticker=state.get("ticker"))
        return {"error": "No final_arguments available for synthesis"}

    # Source-of-truth for pre_debate_confidence is state -- NOT LLM output.
    # Explicit None check (WR-03): silently defaulting to 0 would distort
    # DEBATE-04 success-criterion-4 (post - pre delta) with a wrong baseline.
    pre_debate_confidence = thesis.get("confidence")
    if pre_debate_confidence is None:
        logger.error(
            "debate_synthesis_thesis_missing_confidence",
            ticker=state.get("ticker"),
        )
        return {"error": "Thesis missing 'confidence' field"}
    prompt = format_debate_for_synthesis(state, pre_debate_confidence)

    try:
        limits = get_debate_synthesis_limits()
        result = await debate_synthesis_agent.run(prompt, usage_limits=limits)
    except UsageLimitExceeded as e:
        logger.error(
            "debate_synthesis_budget_exceeded",
            ticker=state["ticker"],
            error=str(e),
        )
        return {"error": f"Debate synthesis budget exceeded: {e}"}

    synthesis = result.output
    # Overwrite LLM values with deterministic / authoritative ones. Immutable
    # update pattern per CLAUDE.md (return a new object; never mutate).
    quality_score = compute_quality_score(
        synthesis.evidence_strength,
        synthesis.logical_consistency,
        synthesis.risk_coverage,
    )
    synthesis = synthesis.model_copy(
        update={
            "quality_score": quality_score,
            "pre_debate_confidence": pre_debate_confidence,
        }
    )
    usage = result.usage
    logger.info(
        "debate_synthesis_complete",
        ticker=state["ticker"],
        pre_conf=pre_debate_confidence,
        post_conf=synthesis.post_debate_confidence,
        quality=quality_score,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )
    return {
        "debate_synthesis": synthesis.model_dump(),
        "thesis": synthesis.revised_thesis.model_dump(),
    }


# ---------------------------------------------------------------------------
# Phase-6 risk manager node: deterministic-first veto with LLM advisory
# rationale. Pattern 2 from 06-RESEARCH.md; RationaleOnly supersession
# (the agent's schema lacks a status field, so the LLM CANNOT author the
# decision). First-violation-wins ordering:
#     exclusions -> position_size -> sector -> correlation -> drawdown
# The LLM is still called on violations so the audit trail has a
# human-readable rationale, but status / constraint / observed / limit
# are set by Python via a fresh ``RiskAssessment(...)`` construction --
# ``result.output.model_copy`` would widen the LLM attack surface and is
# explicitly NOT used (negative grep in 06-05-PLAN.md acceptance).
# ---------------------------------------------------------------------------


def _conviction_from_confidence(confidence: int) -> Literal["low", "medium", "high"]:
    """Bucket ThesisOutput.confidence (0-100) into low/medium/high."""
    if confidence >= 75:
        return "high"
    if confidence >= 50:
        return "medium"
    return "low"


async def risk_manager_node(state: DebatePipelineState, deps: RiskDeps) -> dict:
    """Phase-6 Risk Manager node -- deterministic checks + advisory rationale.

    Threat mitigations:
        T-06-02  (veto bypass): ``status`` is set via ``RiskAssessment(...,
                 status=status, ...)`` AFTER the agent runs; the agent's
                 output schema (:class:`RationaleOnly`) has no status
                 field, so the LLM cannot even emit one.
        T-06-04  (policy drift): ``policy_sha`` is persisted on every
                 emitted :class:`RiskAssessment` and logged in the
                 structlog event.
        T-06-05  (div-by-zero): ``risk/drawdown.py`` guards handle NaN
                 and all-zero return series without raising.
        Pitfall 1: LLM rationale is advisory; deterministic result wins.
        Pitfall 2: policy + portfolio loaded INSIDE the node, keyed on
                   ``state['as_of_date']`` for temporal correctness.
        Pitfall 3: empty portfolio + candidate evaluates candidate-only
                   drawdown (``check_drawdown`` handles this branch).
        Pitfall 4: insufficient price history short-circuits with a named
                   ``insufficient_price_history`` violation.
        Pitfall 7: router fails closed on missing assessment (see
                   :func:`route_after_risk`).

    Args:
        state: DebatePipelineState carrying ``thesis`` (post-debate),
            ``candidate_metadata`` (optional sector + instrument_type),
            ``ticker``, and ``as_of_date``.
        deps: Bound :class:`RiskDeps` (db_session, returns DataFrame, and
            either a pre-built policy or a policy path).

    Returns:
        ``{"risk_assessment": RiskAssessment.model_dump()}`` on success,
        ``{"error": ...}`` when the thesis is missing / malformed or the
        LLM budget is exceeded, or ``{}`` when an upstream error has
        already short-circuited the pipeline.
    """
    if state.get("error"):
        return {}
    thesis = state.get("thesis")
    if thesis is None:
        logger.error("risk_no_thesis", ticker=state.get("ticker"))
        return {"error": "No thesis available for risk check"}

    # ThesisOutput (src/ai_hedge_fund/schemas/agents.py::ThesisOutput) has
    # ticker, bull_case, bear_case, confidence: int (0-100), risk_factors.
    # Explicitly NO sector / instrument_type -- those arrive via
    # state["candidate_metadata"]. Missing confidence is a schema bug
    # upstream; do not default to 0.
    confidence = thesis.get("confidence")
    if confidence is None:
        logger.error("risk_thesis_missing_confidence", ticker=state.get("ticker"))
        return {"error": "Thesis missing 'confidence' field"}
    conviction = _conviction_from_confidence(int(confidence))

    # Policy + portfolio load INSIDE the node (Pitfall 2).
    policy = deps.policy if deps.policy is not None else load_policy(deps.policy_path)
    policy_sha = compute_policy_sha(policy)
    portfolio = load_portfolio(deps.db_session, state["as_of_date"])

    # state["ticker"] is the pipeline-level source of truth; thesis.ticker is
    # LLM-produced and can drift under stubs or prompt variance.
    candidate_ticker = state["ticker"]
    # Candidate sector + instrument_type come from state (NOT ThesisOutput).
    candidate_meta = state.get("candidate_metadata") or {}
    candidate_sector = candidate_meta.get("sector") or "Unknown"
    candidate_instrument_type = candidate_meta.get("instrument_type") or "equity"
    candidate_size_pct = derive_candidate_size_pct(conviction, policy)

    # 5 deterministic checks in fixed order. We run ALL of them so the
    # node can aggregate per-check utilization ratios into
    # ``RiskAssessment.utilization`` (08-RESEARCH.md A9), but the
    # "first violation wins" contract is preserved by walking the
    # ordered results list and picking the first non-None violation.
    check_results: list[CheckResult] = [
        check_exclusions(candidate_sector, candidate_instrument_type, policy),
        check_position_size(candidate_size_pct, policy),
        check_sector_concentration(candidate_sector, candidate_size_pct, portfolio, policy),
        check_correlation(candidate_ticker, portfolio, deps.returns, policy),
        check_drawdown(candidate_ticker, candidate_size_pct, portfolio, deps.returns, policy),
    ]
    violation: Violation | None = next(
        (cr.violation for cr in check_results if cr.violation is not None),
        None,
    )
    # max() over the ratios; clamp to [0, 1]. On VETOED, the offending
    # ratio is naturally >= 1.0 and clamps. On APPROVED, the largest
    # surviving ratio reflects how close the candidate is to the tightest
    # binding constraint -- exactly the signal the Phase-8 risk_score wants.
    utilization = min(1.0, max((cr.ratio for cr in check_results), default=0.0))
    utilization = max(0.0, utilization)
    status: Literal["APPROVED", "VETOED"] = "VETOED" if violation else "APPROVED"

    # Call LLM for rationale (advisory) -- even on veto, for audit trail.
    prompt = format_risk_context_for_rationale(
        thesis=thesis,
        status=status,
        violation=violation,
        portfolio=portfolio,
        policy=policy,
    )
    try:
        limits = get_risk_manager_limits()
        result = await risk_manager_agent.run(prompt, usage_limits=limits)
    except UsageLimitExceeded as e:
        logger.error(
            "risk_manager_budget_exceeded",
            ticker=state["ticker"],
            error=str(e),
        )
        return {"error": f"Risk manager budget exceeded: {e}"}

    # DETERMINISTIC OVERWRITE -- LLM status value is DISCARDED. The agent's
    # RationaleOnly schema has no status field, so this is belt-and-braces:
    # even if the agent were replaced with a wider schema, the node's
    # Python-authored ``status`` and ``utilization`` are what ship.
    assessment = RiskAssessment(
        ticker=candidate_ticker,
        status=status,
        constraint_violated=violation.name if violation else None,
        observed=violation.observed if violation else None,
        limit=violation.limit if violation else None,
        utilization=utilization,
        rationale=result.output.rationale,
        policy_sha=policy_sha,
    )

    usage = result.usage
    event_name = "risk_manager_complete" if status == "APPROVED" else "risk_manager_veto"
    logger.info(
        event_name,
        ticker=state["ticker"],
        status=status,
        constraint_violated=assessment.constraint_violated,
        observed=assessment.observed,
        limit=assessment.limit,
        utilization=utilization,
        policy_sha=policy_sha,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )
    return {"risk_assessment": assessment.model_dump()}


def route_after_risk(state: DebatePipelineState) -> Literal["signal", "__end__"]:
    """Fail-closed router: APPROVED -> signal; VETOED or missing -> __end__.

    Pitfall 7 mitigation: any state where ``risk_assessment`` is absent,
    ``None``, or lacks a ``status`` key routes to ``__end__``. A router
    that defaulted to ``signal`` would silently approve a broken
    upstream, bypassing the veto entirely.
    """
    assessment = state.get("risk_assessment")
    if assessment is None:
        return "__end__"
    return "signal" if assessment.get("status") == "APPROVED" else "__end__"


async def memory_recall_node(state: DebatePipelineState, deps: MemoryDeps) -> dict:
    """Phase-7 pre-fan-out recall: load episodic_hits + beliefs_consulted.

    Called BEFORE the three parallel analysts so every downstream agent
    sees the same deterministic prior-work set in state.

    Threat mitigations / contract:
        T-07-20 (temporal leakage): delegates to :func:`query_episodic`
                 which enforces ``as_of_date <= target``. A future-dated
                 row (e.g., 2099-01-01) MUST NOT be returned when
                 ``state['as_of_date']`` is earlier.
        T-07-21 (silent human-edit override): uses :func:`load_belief`
                 unchanged. The ``human_edited`` flag and the human-edited
                 ``confidence`` value are preserved verbatim into
                 ``state['beliefs_consulted']`` so the downstream analyst
                 prompts reflect the human override (MEM-03 read path).
        Short-circuit: returns ``{}`` when ``state['error']`` is set.
        Missing belief files are tolerated: returns
        ``beliefs_consulted=[]`` rather than raising.

    Args:
        state: DebatePipelineState carrying ``ticker``, ``as_of_date``,
            and (optionally) ``candidate_metadata.sector``.
        deps: Bound :class:`MemoryDeps` (db_session, beliefs_path, recall_limit).

    Returns:
        ``{"episodic_hits": [...], "beliefs_consulted": [...]}`` on success,
        ``{}`` on upstream error.
    """
    if state.get("error"):
        return {}

    ticker = state["ticker"]
    as_of_date = state["as_of_date"]
    meta = state.get("candidate_metadata") or {}
    sector = meta.get("sector") or "Unknown"

    # query_episodic raises ValueError when neither ticker nor sector is
    # supplied; we always pass ticker, so the guard is purely defensive.
    sector_filter = sector if sector != "Unknown" else None
    hits = query_episodic(
        deps.db_session,
        as_of_date=as_of_date,
        ticker=ticker,
        sector=sector_filter,
        limit=deps.recall_limit,
    )
    episodic_hits = [hit.model_dump(mode="json") for hit in hits]

    beliefs_consulted: list[dict] = []
    # Ticker-level belief (optional -- missing file is fine).
    try:
        ticker_path = belief_path_for_ticker(deps.beliefs_path, ticker)
    except ValueError:
        # Invalid ticker format for the belief path regex; recall still
        # works because query_episodic accepts arbitrary strings.
        ticker_path = None

    if ticker_path is not None and ticker_path.is_file():
        belief, _raw = load_belief(ticker_path)
        beliefs_consulted.append(belief.model_dump(mode="json"))

    # Sector-level belief (optional). Layout: beliefs_path/sectors/<Sector>.yaml.
    # The sector string flows from state -- a caller that bypasses the
    # Pydantic validator and pushes a raw dict (LangGraph accepts dicts for
    # TypedDict states) could set ``sector="../tickers/AAPL"`` and trick the
    # path join. ``belief_path_for_sector`` applies the same defense-in-depth
    # regex guard that ``belief_path_for_ticker`` uses for the ticker subtree
    # (T-07-11 analogue).
    if sector != "Unknown":
        try:
            sector_path = belief_path_for_sector(deps.beliefs_path, sector)
        except ValueError:
            sector_path = None
        if sector_path is not None and sector_path.is_file():
            sector_belief, _raw = load_belief(sector_path)
            beliefs_consulted.append(sector_belief.model_dump(mode="json"))

    logger.info(
        "memory_recall_complete",
        ticker=ticker,
        as_of_date=as_of_date,
        sector=sector,
        episodic_hits=len(episodic_hits),
        beliefs_consulted=len(beliefs_consulted),
    )
    return {
        "episodic_hits": episodic_hits,
        "beliefs_consulted": beliefs_consulted,
    }


async def episodic_store_node(state: DebatePipelineState, deps: MemoryDeps) -> dict:
    """Phase-7 pipeline-end recorder: append an EpisodicMemory row (MEM-01 write).

    Fires on BOTH APPROVED and VETOED paths -- vetoes are the richest
    learning signal (07-RESEARCH.md Open Question 1 recommendation). The
    stored row links Phase 6's ``policy_sha`` for cross-phase audit (Phase
    6 plan 06-06).

    policy_sha authoritative copy:
        ``row.policy_sha`` (the dedicated column) is the AUTHORITATIVE
        audit SHA. ``row.payload["risk_assessment"]["policy_sha"]`` is a
        convenience snapshot for offline inspection. Consumers MUST read
        the column, not the payload. The two are equal on every write
        (tested by ``test_episodic_store_policy_sha_authoritative_column_matches_payload``).

    Contract:
        - Short-circuits on upstream error (returns ``{}`` -- no DB write).
        - Always commits; never raises unless the DB layer raises.
        - payload includes thesis, signal (may be ``None`` on veto),
          risk_assessment (may be empty), plus counts of prior hits and
          beliefs consulted (for future retrospective analysis).

    Args:
        state: Post-debate DebatePipelineState with ``thesis``,
            ``signal`` (may be None), ``risk_assessment``,
            ``candidate_metadata`` (optional), ``ticker``, and ``as_of_date``.
        deps: Bound :class:`MemoryDeps` (db_session used for the INSERT).

    Returns:
        ``{"episodic_stored_id": <int>}`` on success, ``{}`` on upstream error.
    """
    if state.get("error"):
        return {}

    thesis = state.get("thesis") or {}
    signal = state.get("signal")
    risk = state.get("risk_assessment") or {}
    meta = state.get("candidate_metadata") or {}

    # state["as_of_date"] is an ISO-8601 string (DebatePipelineState
    # contract -- JSON-serialisable for LangGraph checkpoints). The
    # EpisodicMemory.as_of_date column is DateTime(timezone=True) (from
    # DualTimestampMixin); SQLite's DateTime binder rejects strings.
    # _normalise_as_of is the same helper the episodic CSV seeder uses
    # (ai_hedge_fund.memory.episodic) and converts str|date|datetime to
    # a tz-aware UTC datetime.
    as_of_dt = _normalise_as_of(state["as_of_date"])
    row = EpisodicMemory(
        ticker=state["ticker"],
        sector=meta.get("sector") or "Unknown",
        record_type="analysis",
        signal_direction=(signal or {}).get("direction"),
        confidence=thesis.get("confidence"),
        outcome_pct=None,
        linked_analysis_id=None,
        policy_sha=risk.get("policy_sha"),
        as_of_date=as_of_dt,
        payload={
            "schema_version": 1,
            "thesis": thesis,
            "signal": signal,
            "risk_assessment": risk,
            "episodic_hits_count": len(state.get("episodic_hits") or []),
            "beliefs_consulted_count": len(state.get("beliefs_consulted") or []),
        },
    )
    deps.db_session.add(row)
    deps.db_session.commit()

    logger.info(
        "episodic_store_complete",
        ticker=state["ticker"],
        as_of_date=state["as_of_date"],
        episodic_stored_id=row.id,
        policy_sha=risk.get("policy_sha"),
        signal_direction=(signal or {}).get("direction"),
        risk_status=risk.get("status"),
    )
    return {"episodic_stored_id": row.id}


# =========================
# Phase 8: output, review, store, router (SIG-01 / SIG-03 / SIG-04)
# =========================


async def output_node(state: DebatePipelineState, deps: ReviewDeps) -> dict:
    """Assemble ``FinalSignalOutput`` from authoritative state (Phase 8 SIG-01).

    Runs AFTER ``episodic_store_node`` so ``state['episodic_stored_id']`` is
    available for ``thesis_link``. Pure Python; zero LLM. Short-circuits on
    upstream error.

    Writes: ``final_signal`` (``FinalSignalOutput.model_dump()``).

    Threat mitigations:
        T-08-12 (LLM-authored risk_score): the assembler is purely
            deterministic via :func:`assemble_final_signal` +
            :func:`derive_risk_score`; no PydanticAI ``Agent.run`` is
            invoked here.
    """
    if state.get("error"):
        return {}
    if state.get("signal") is None:
        logger.error("output_no_signal", ticker=state.get("ticker"))
        return {"error": "No signal available for output assembly"}
    if state.get("episodic_stored_id") is None:
        logger.error("output_no_episodic_id", ticker=state.get("ticker"))
        return {"error": ("No episodic_stored_id available; output_node requires with_memory=True")}

    # Resolve review_policy from deps (policy takes precedence; policy_path
    # is loaded by the pipeline builder, but we keep this fallback for the
    # rare case the node is invoked outside build_debate_pipeline -- e.g.,
    # unit tests that pass policy_path directly).
    policy: ReviewPolicy
    if deps.policy is not None:
        policy = deps.policy
    else:
        # Lazy import to avoid pulling load_review_policy into the hot path.
        from ai_hedge_fund.review.policy import load_review_policy

        assert deps.policy_path is not None  # XOR enforced by ReviewDeps
        policy = load_review_policy(deps.policy_path)

    review_policy_sha = compute_review_policy_sha(policy)

    final_signal = assemble_final_signal(
        dict(state),
        review_policy_sha=review_policy_sha,
        episodic_id=state["episodic_stored_id"],
        # review_status defaults to NOT_REQUIRED; the human_review_node
        # writes a separate review_decision key when the gate fires.
    )

    logger.info(
        "output_complete",
        ticker=state["ticker"],
        direction=final_signal.direction,
        conviction=final_signal.conviction,
        review_status=final_signal.review_status,
        review_policy_sha=review_policy_sha,
    )
    return {"final_signal": final_signal.model_dump(mode="json")}


async def human_review_node(state: DebatePipelineState) -> dict:
    """Pause the pipeline until a human supplies a ``ReviewDecision`` (SIG-03).

    Calls :func:`langgraph.types.interrupt` -- the LangGraph checkpointer
    persists state; the caller resumes via ``Command(resume=decision_dict)``.
    This node does NOT read stdin; stdin handling is the CLI's job
    (``run_analysis.py`` in Plan 08-04).

    Writes: ``review_decision`` (``ReviewDecision.model_dump()``).

    Threat mitigations:
        T-08-03 (silent bypass): this function calls ``interrupt(...)``
            literally. Any refactor that removes the call breaks the
            review gate; ``test_interrupt_primitive_is_invoked_in_source``
            greps the source as a defense-in-depth check.
        T-08-04 (malformed resume): the resumed value is validated via
            ``ReviewDecision.model_validate``; bad payloads raise
            ``pydantic.ValidationError`` instead of being silently
            accepted.
    """
    if state.get("error"):
        return {}
    signal = state.get("final_signal")
    if signal is None:
        logger.error("human_review_no_final_signal", ticker=state.get("ticker"))
        return {"error": "No final_signal available for review"}

    review_request = {
        "ticker": state["ticker"],
        "as_of_date": state["as_of_date"],
        "signal": signal,
        "thesis": state.get("thesis"),
        "debate": {
            "bull_case": state.get("bull_case"),
            "bear_case": state.get("bear_case"),
            "rebuttal": state.get("rebuttal"),
            "final_arguments": state.get("final_arguments"),
            "synthesis": state.get("debate_synthesis"),
        },
        "risk_assessment": state.get("risk_assessment"),
        "episodic_hits": state.get("episodic_hits") or [],
        "beliefs_consulted": state.get("beliefs_consulted") or [],
    }

    # T-08-03: PAUSES the graph; LangGraph persists state via checkpointer.
    decision_raw = interrupt(review_request)

    # T-08-04: validate; malformed raises ValidationError.
    decision = ReviewDecision.model_validate(decision_raw)

    logger.info(
        "human_review_decision_received",
        ticker=state["ticker"],
        status=decision.status,
        reviewer_id=decision.reviewer_id,
        review_policy_sha=decision.review_policy_sha,
    )
    return {"review_decision": decision.model_dump(mode="json")}


async def review_store_node(state: DebatePipelineState, deps: ReviewDeps) -> dict:
    """Append a ``record_type='review'`` row to ``episodic_memory`` (SIG-04).

    Runs on BOTH the reviewed path (APPROVED / REJECTED) AND the
    NOT_REQUIRED path (conviction below threshold -- no interrupt fired).
    Writing a row on every output-bearing flow keeps the audit trail
    uniform (Pitfall G).

    Threat mitigations:
        T-08-05 (history rewrite): NEVER mutates the analysis row -- the
            review row is a brand-new ``EpisodicMemory`` insert with
            ``linked_analysis_id`` referencing the analysis row's id.
            The session is committed, never merged or updated.
    """
    if state.get("error"):
        return {}

    decision = state.get("review_decision")
    linked_id = state.get("episodic_stored_id")
    status = (decision or {}).get("status") or "NOT_REQUIRED"
    as_of_dt = _normalise_as_of(state["as_of_date"])
    final_signal_dict = state.get("final_signal") or {}

    row = EpisodicMemory(
        ticker=state["ticker"],
        sector=(state.get("candidate_metadata") or {}).get("sector") or "Unknown",
        record_type="review",
        signal_direction=final_signal_dict.get("direction"),
        confidence=final_signal_dict.get("conviction"),
        outcome_pct=None,
        linked_analysis_id=linked_id,
        policy_sha=(state.get("risk_assessment") or {}).get("policy_sha"),
        as_of_date=as_of_dt,
        payload={
            "schema_version": 1,
            "review_status": status,
            "review_decision": decision,
            "review_policy_sha": (decision or {}).get("review_policy_sha")
            or final_signal_dict.get("review_policy_sha"),
            "linked_analysis_id": linked_id,
            "final_signal": final_signal_dict,
        },
    )
    deps.db_session.add(row)
    deps.db_session.commit()

    logger.info(
        "review_store_complete",
        ticker=state["ticker"],
        review_status=status,
        linked_analysis_id=linked_id,
        review_row_id=row.id,
        review_policy_sha=(decision or {}).get("review_policy_sha"),
    )
    return {"review_stored_id": row.id}


def route_before_review(
    state: DebatePipelineState,
) -> Literal["human_review", "review_store"]:
    """Fail-closed router: ``conviction >= threshold -> human_review``;
    else ``review_store``.

    Mirror of :func:`route_after_risk` (Phase 6). Fail-closed: missing
    threshold or missing ``final_signal`` routes to ``human_review`` (the
    stricter branch; never auto-approves with ambiguous state).

    The ``_review_threshold`` key is injected into state by the pipeline
    caller (CLI in Plan 08-04; tests inject directly) so the router can
    compare without needing deps access.
    """
    signal = state.get("final_signal") or {}
    threshold = state.get("_review_threshold")
    conviction = signal.get("conviction")
    if threshold is None or conviction is None:
        return "human_review"
    return "human_review" if conviction >= threshold else "review_store"
