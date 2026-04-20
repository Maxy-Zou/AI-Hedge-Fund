"""Technical/Quant analyst agent with price data tool only.

Specializes in technical and quantitative equity analysis: momentum
indicators, volatility metrics, and trend signals derived exclusively
from tool-provided price data. Uses the same ResearchDeps dependency
injection pattern as the Phase 3 research agent.

Tool domain (1 tool):
    get_price_data -- Historical price data with return and volatility stats

Threat mitigations:
    T-04-01: source_tool required on every TechnicalIndicator (schema-enforced).
    T-04-02: System prompt explicitly forbids describing price patterns,
             support/resistance levels, or chart formations unless derived
             from tool-provided data.
    T-04-03: as_of_date enforced via ResearchDeps; system prompt restricts
             knowledge to as_of_date.
    T-04-04: UsageLimits via get_technical_limits() on every run.
    T-04-05: Only 1 domain-relevant tool registered (no cross-domain access).
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.agents.research import ResearchDeps
from ai_hedge_fund.data.tools import get_price_history
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import TechnicalAnalysis

TECHNICAL_SYSTEM_PROMPT_TEMPLATE = (
    "You are a senior quantitative/technical analyst producing a technical analysis "
    "for {ticker}.\n"
    "\n"
    "CRITICAL RULES:\n"
    "1. You MUST call get_price_data before forming any conclusions.\n"
    "2. NEVER describe price patterns, support/resistance levels, or chart formations "
    "unless derived from tool-provided data. You are NOT allowed to use your training "
    "knowledge about price history -- only data from get_price_data.\n"
    "3. You are analyzing as of {as_of_date}. You have NO knowledge of events after "
    "this date. Do not reference any events or data after {as_of_date}.\n"
    "4. Every indicator MUST include source_tool='get_price_data' to confirm it came "
    "from tool output.\n"
    "5. Provide at least 2 technical indicators (e.g., RSI, moving averages, "
    "volatility measures) with tool citations.\n"
    "6. Provide a momentum_assessment and volatility_assessment based on tool data.\n"
    "7. Bull and bear factors must each have at least 1 entry backed by tool evidence.\n"
    "8. Confidence score (0-100) should reflect evidence strength from tool data, "
    "not your prior beliefs about the company.\n"
)

technical_agent: Agent[ResearchDeps, TechnicalAnalysis] = Agent(
    ModelTier.ANALYSIS.value,
    output_type=TechnicalAnalysis,
    deps_type=ResearchDeps,
    retries=2,
)


@technical_agent.system_prompt
def technical_system_prompt(ctx: RunContext[ResearchDeps]) -> str:
    """Render the system prompt with per-run ticker and as_of_date."""
    return TECHNICAL_SYSTEM_PROMPT_TEMPLATE.format(
        ticker=ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date.isoformat(),
    )


@technical_agent.tool
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


def get_technical_limits() -> UsageLimits:
    """Return UsageLimits for the technical agent (ANALYSIS tier, Sonnet)."""
    return get_usage_limits(ModelTier.ANALYSIS)
