"""Research agent with tool-augmented investment thesis generation.

Uses PydanticAI dependency injection (``RunContext[ResearchDeps]``) to pass
pipeline context (ticker, as_of_date, db_session, settings) into thin tool
wrappers that delegate to the Phase 2 data tool functions. The LLM
controls tool *selection* and optional query parameters (e.g., how many
lookback days), but it never controls the ticker or as_of_date --
those come from the pipeline state, not the model.

Threat mitigations:
    T-03-01: Tampering -- system prompt + ThesisPoint schema forbid
             LLM-generated financial figures.
    T-03-02: Information disclosure (temporal leak) -- system prompt
             restricts knowledge to as_of_date; every tool enforces
             ``@enforce_as_of_date`` at the data boundary.
    T-03-03: Tampering -- ticker/as_of_date injected via ResearchDeps
             (RunContext), not exposed as LLM-controlled parameters.
    T-03-04: DoS -- tool wrappers return summary_text only (no raw data);
             UsageLimits enforced on every run via get_research_limits().
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits
from sqlalchemy.orm import Session

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.config import AppSettings
from ai_hedge_fund.data.tools import (
    get_filing_sections,
    get_financial_summary,
    get_insider_clusters,
    get_macro_context,
    get_news_sentiment,
    get_price_history,
)
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import ThesisOutput


@dataclass(frozen=True)
class ResearchDeps:
    """Immutable dependency container for the research agent.

    Carries pipeline context (ticker, as_of_date) and infrastructure
    handles (db_session, settings) through to tool calls via
    ``RunContext``. The LLM must never control these values -- they come
    from pipeline state.

    Attributes:
        ticker: Stock ticker symbol being analyzed (e.g., "AAPL").
        as_of_date: Temporal cutoff date; no data after this date is
            considered (prevents look-ahead bias).
        db_session: Optional SQLAlchemy session for cache reads/writes.
        settings: Optional AppSettings for API keys; resolved from env
            when None.
    """

    ticker: str
    as_of_date: date
    db_session: Session | None = None
    settings: AppSettings | None = None


RESEARCH_SYSTEM_PROMPT_TEMPLATE = (
    "You are a senior equity research analyst producing an investment thesis for {ticker}.\n"
    "\n"
    "CRITICAL RULES:\n"
    "1. NEVER state a financial figure (revenue, earnings, price, ratio, growth rate) unless "
    "it came from a tool call. If you have not called a tool for a metric, do not mention it.\n"
    "2. You are analyzing as of {as_of_date}. You have NO knowledge of events after this date. "
    "Do not reference any events, earnings, or data that occurred after {as_of_date}.\n"
    "3. You MUST call get_financials and get_price_data at minimum before forming your thesis.\n"
    "4. You MUST call at least one of: get_insider_activity, get_sentiment, "
    "get_macro_environment.\n"
    "5. Every bull and bear case point MUST cite the specific tool and data that supports it "
    "in the source_tool and evidence fields.\n"
    "6. Your bull case needs at least 3 points, bear case at least 3 points, "
    "risk factors at least 2.\n"
    "7. Confidence score (0-100) should reflect evidence strength, not your prior beliefs "
    "about the company.\n"
)

research_agent: Agent[ResearchDeps, ThesisOutput] = Agent(
    ModelTier.ANALYSIS.value,
    output_type=ThesisOutput,
    deps_type=ResearchDeps,
    retries=2,
)


@research_agent.system_prompt
def research_system_prompt(ctx: RunContext[ResearchDeps]) -> str:
    """Render the system prompt with per-run ticker and as_of_date."""
    return RESEARCH_SYSTEM_PROMPT_TEMPLATE.format(
        ticker=ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date.isoformat(),
    )


@research_agent.tool
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


@research_agent.tool
def get_financials(ctx: RunContext[ResearchDeps]) -> str:
    """Get the latest XBRL financial summary (revenue, net income, EPS, margins).

    Returns a natural language summary of the most recent XBRL financial
    data with year-over-year comparisons. Numbers in the summary are the
    only financial figures the agent should cite.
    """
    result = get_financial_summary(
        ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date,
        db_session=ctx.deps.db_session,
        settings=ctx.deps.settings,
    )
    return result["summary_text"]


@research_agent.tool
def get_price_data(
    ctx: RunContext[ResearchDeps],
    lookback_days: int = 252,
) -> str:
    """Get historical price data with return, volatility, and 52-week range.

    Args:
        lookback_days: Number of calendar days to look back (default 252 ~= 1 year).

    Returns:
        Natural language summary of price performance plus key stats.
    """
    result = get_price_history(
        ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date,
        lookback_days=lookback_days,
        db_session=ctx.deps.db_session,
        settings=ctx.deps.settings,
    )
    # Return summary_text + stats only -- omit the raw prices list to
    # stay within the token budget (T-03-04).
    return f"{result['summary_text']}\n\nStats: {result['stats']}"


@research_agent.tool
def get_insider_activity(
    ctx: RunContext[ResearchDeps],
    lookback_days: int = 90,
) -> str:
    """Get insider purchase clusters from SEC Form 4 filings.

    Args:
        lookback_days: How far back to search for insider trades (default 90).

    Returns:
        Natural language summary of insider cluster buys, if any.
    """
    result = get_insider_clusters(
        ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date,
        lookback_days=lookback_days,
        db_session=ctx.deps.db_session,
        settings=ctx.deps.settings,
    )
    return result["summary_text"]


@research_agent.tool
def get_sentiment(
    ctx: RunContext[ResearchDeps],
    lookback_days: int = 7,
) -> str:
    """Get recent news sentiment for the company.

    Args:
        lookback_days: Number of days of news to consider (default 7).

    Returns:
        Natural language summary of news headlines and average sentiment.
    """
    result = get_news_sentiment(
        ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date,
        lookback_days=lookback_days,
        db_session=ctx.deps.db_session,
        settings=ctx.deps.settings,
    )
    return result["summary_text"]


@research_agent.tool
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


def get_research_limits() -> UsageLimits:
    """Return UsageLimits for the research agent (ANALYSIS tier, Sonnet)."""
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
