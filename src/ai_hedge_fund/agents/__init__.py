"""PydanticAI agent layer with factory functions, budget enforcement, and concrete agents.

Re-exports:
    create_agent: Factory for PydanticAI agents with model-tier routing
    get_usage_limits: Per-tier token budget limits as PydanticAI UsageLimits
    PipelineBudgetTracker: Immutable accumulator for pipeline-wide token budgets
    BudgetExceededError: Raised when pipeline budget is exceeded
    AgentUsageRecord: Frozen record of a single agent's token usage
    extraction_agent: Pre-configured Haiku extraction agent
    get_extraction_limits: UsageLimits for extraction tier
    analysis_agent: Pre-configured Sonnet analysis agent
    get_analysis_limits: UsageLimits for analysis tier
"""

from __future__ import annotations

from ai_hedge_fund.agents.analysis import analysis_agent, get_analysis_limits
from ai_hedge_fund.agents.base import (
    AgentUsageRecord,
    BudgetExceededError,
    PipelineBudgetTracker,
    create_agent,
    get_usage_limits,
)
from ai_hedge_fund.agents.extraction import extraction_agent, get_extraction_limits

__all__ = [
    "AgentUsageRecord",
    "BudgetExceededError",
    "PipelineBudgetTracker",
    "analysis_agent",
    "create_agent",
    "extraction_agent",
    "get_analysis_limits",
    "get_extraction_limits",
    "get_usage_limits",
]
