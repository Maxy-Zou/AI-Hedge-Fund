"""Sentiment analyst agent with news sentiment and insider activity tools.

Specializes in market sentiment analysis: news sentiment scoring and
insider trading activity detection. Uses the same ResearchDeps dependency
injection pattern as the Phase 3 research agent.

Tool domain (2 tools):
    get_sentiment -- News sentiment summary from Finnhub
    get_insider_activity -- Insider purchase clusters from SEC Form 4

Threat mitigations:
    T-04-01: source_tool required on every SentimentComponent (schema-enforced).
    T-04-03: as_of_date enforced via ResearchDeps; system prompt restricts
             knowledge to as_of_date.
    T-04-04: UsageLimits via get_sentiment_limits() on every run.
    T-04-05: Only 2 domain-relevant tools registered (no cross-domain access).
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.agents.research import ResearchDeps
from ai_hedge_fund.data.tools import (
    get_insider_clusters,
    get_news_sentiment,
)
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import SentimentAnalysis

SENTIMENT_SYSTEM_PROMPT_TEMPLATE = (
    "You are a senior sentiment analyst producing a sentiment analysis "
    "for {ticker}.\n"
    "\n"
    "CRITICAL RULES:\n"
    "1. You MUST call both get_sentiment and get_insider_activity before forming "
    "your analysis.\n"
    "2. Produce a composite sentiment score from -1.0 (most bearish) to +1.0 "
    "(most bullish) based on all component signals.\n"
    "3. Break down your composite score into individual components, each with its "
    "own score, summary, and source_tool citation.\n"
    "4. You are analyzing as of {as_of_date}. You have NO knowledge of events after "
    "this date. Do not reference any events or data after {as_of_date}.\n"
    "5. Every component MUST include source_tool citing which tool produced the data.\n"
    "6. Provide at least 1 key signal describing a notable sentiment finding.\n"
    "7. Confidence score (0-100) should reflect evidence strength from tool data, "
    "not your prior beliefs.\n"
    "8. If insider activity shows cluster buys, weight this as a strong bullish "
    "signal. If no significant insider activity, note it as neutral.\n"
)

sentiment_agent: Agent[ResearchDeps, SentimentAnalysis] = Agent(
    ModelTier.ANALYSIS.value,
    output_type=SentimentAnalysis,
    deps_type=ResearchDeps,
    retries=2,
)


@sentiment_agent.system_prompt
def sentiment_system_prompt(ctx: RunContext[ResearchDeps]) -> str:
    """Render the system prompt with per-run ticker and as_of_date."""
    return SENTIMENT_SYSTEM_PROMPT_TEMPLATE.format(
        ticker=ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date.isoformat(),
    )


@sentiment_agent.tool
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


@sentiment_agent.tool
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


def get_sentiment_limits() -> UsageLimits:
    """Return UsageLimits for the sentiment agent (ANALYSIS tier, Sonnet)."""
    return get_usage_limits(ModelTier.ANALYSIS)
