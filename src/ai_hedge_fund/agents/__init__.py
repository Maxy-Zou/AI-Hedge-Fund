"""PydanticAI agent layer with factory functions and budget enforcement.

Re-exports:
    create_agent: Factory for PydanticAI agents with model-tier routing
    get_usage_limits: Per-tier token budget limits as PydanticAI UsageLimits
    PipelineBudgetTracker: Immutable accumulator for pipeline-wide token budgets
    BudgetExceededError: Raised when pipeline budget is exceeded
    AgentUsageRecord: Frozen record of a single agent's token usage
"""

from __future__ import annotations

from ai_hedge_fund.agents.base import (
    AgentUsageRecord,
    BudgetExceededError,
    PipelineBudgetTracker,
    create_agent,
    get_usage_limits,
)

__all__ = [
    "AgentUsageRecord",
    "BudgetExceededError",
    "PipelineBudgetTracker",
    "create_agent",
    "get_usage_limits",
]
