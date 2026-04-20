"""Fundamental analyst agent with SEC filing and financial data tools.

Specializes in fundamental equity analysis: valuation metrics from XBRL
financial data, SEC filing RAG for qualitative evidence, and macro context
for valuation framing. Uses the same ResearchDeps dependency injection
pattern as the Phase 3 research agent.

Tool domain (3 tools):
    fetch_filings -- SEC filing sections (10-K, 10-Q)
    get_financials -- XBRL financial summary (revenue, EPS, margins)
    get_macro_environment -- Macroeconomic context (rates, CPI, GDP)

Threat mitigations:
    T-04-01: source_tool required on every ValuationMetric (schema-enforced).
    T-04-03: as_of_date enforced via ResearchDeps; system prompt restricts
             knowledge to as_of_date.
    T-04-04: UsageLimits via get_fundamental_limits() on every run.
    T-04-05: Only 3 domain-relevant tools registered (no cross-domain access).
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.agents.research import ResearchDeps
from ai_hedge_fund.data.tools import (
    get_filing_sections,
    get_financial_summary,
    get_macro_context,
)
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import FundamentalAnalysis

FUNDAMENTAL_SYSTEM_PROMPT_TEMPLATE = (
    "You are a senior fundamental equity analyst producing a fundamental analysis "
    "for {ticker}.\n"
    "\n"
    "CRITICAL RULES:\n"
    "1. You MUST call get_financials to obtain valuation metrics. NEVER invent "
    "financial figures -- every number must come from a tool call.\n"
    "2. You MUST call fetch_filings to obtain SEC filing evidence. Cite specific "
    "filing sections in your filing_citations.\n"
    "3. You are analyzing as of {as_of_date}. You have NO knowledge of events after "
    "this date. Do not reference any events, earnings, or data after {as_of_date}.\n"
    "4. Every valuation_metric MUST include source_tool citing which tool produced it.\n"
    "5. Provide at least 2 valuation metrics (e.g., P/E, EV/EBITDA) with tool citations.\n"
    "6. Provide at least 1 filing citation referencing a specific SEC filing section.\n"
    "7. Bull and bear factors must each have at least 1 entry backed by tool evidence.\n"
    "8. Confidence score (0-100) should reflect evidence strength from tool data, "
    "not your prior beliefs about the company.\n"
    "9. Call get_macro_environment for macro context that may impact valuation.\n"
)

fundamental_agent: Agent[ResearchDeps, FundamentalAnalysis] = Agent(
    ModelTier.ANALYSIS.value,
    output_type=FundamentalAnalysis,
    deps_type=ResearchDeps,
    retries=2,
)


@fundamental_agent.system_prompt
def fundamental_system_prompt(ctx: RunContext[ResearchDeps]) -> str:
    """Render the system prompt with per-run ticker and as_of_date."""
    return FUNDAMENTAL_SYSTEM_PROMPT_TEMPLATE.format(
        ticker=ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date.isoformat(),
    )


@fundamental_agent.tool
def fetch_filings(
    ctx: RunContext[ResearchDeps],
    form_type: str = "10-K",
    max_filings: int = 3,
) -> str:
    """Retrieve SEC filing sections (10-K, 10-Q) for the company.

    Args:
        form_type: SEC form type -- "10-K" (annual) or "10-Q" (quarterly).
        max_filings: Maximum number of recent filings to include.

    Returns:
        Formatted filing sections text suitable for LLM consumption.
    """
    results = get_filing_sections(
        ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date,
        form_type=form_type,
        max_filings=max_filings,
        db_session=ctx.deps.db_session,
        settings=ctx.deps.settings,
    )
    return _format_filings_for_llm(results)


@fundamental_agent.tool
def get_financials(ctx: RunContext[ResearchDeps]) -> str:
    """Get the latest XBRL financial summary (revenue, net income, EPS, margins).

    Returns a natural language summary of the most recent XBRL financial
    data with year-over-year comparisons.
    """
    result = get_financial_summary(
        ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date,
        db_session=ctx.deps.db_session,
        settings=ctx.deps.settings,
    )
    return result["summary_text"]


@fundamental_agent.tool
def get_macro_environment(ctx: RunContext[ResearchDeps]) -> str:
    """Get macroeconomic context (rates, inflation, GDP, yield curve).

    Macro data is market-wide and does not depend on ticker.

    Returns:
        Natural language summary of the macro environment as of the
        analysis date.
    """
    result = get_macro_context(
        as_of_date=ctx.deps.as_of_date,
        db_session=ctx.deps.db_session,
        settings=ctx.deps.settings,
    )
    return result["summary_text"]


def get_fundamental_limits() -> UsageLimits:
    """Return UsageLimits for the fundamental agent (ANALYSIS tier, Sonnet)."""
    return get_usage_limits(ModelTier.ANALYSIS)


def _format_filings_for_llm(results: list[dict]) -> str:
    """Format SEC filing sections into a readable text block.

    Joins section headers and bodies from each returned filing. Keeps
    output concise to preserve token budget.

    Args:
        results: Filing result dicts from get_filing_sections.

    Returns:
        Human-readable, LLM-friendly text summary.
    """
    if not results:
        return "No filings available for the requested form type and date range."

    blocks: list[str] = []
    for result in results:
        header = (
            f"Filing {result.get('accession_no', 'unknown')} "
            f"({result.get('form_type', '?')}, "
            f"filed {result.get('filing_date', '?')})"
        )
        sections = result.get("sections", {})
        section_texts = [f"## {name}\n{text}" for name, text in sections.items()]
        blocks.append(f"{header}\n\n" + "\n\n".join(section_texts))
    return "\n\n---\n\n".join(blocks)
