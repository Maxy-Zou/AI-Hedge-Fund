"""Agent factory with budget enforcement and pipeline budget tracking.

Provides:
    create_agent: Factory that creates PydanticAI Agent instances with
        model-tier routing via ModelTier enum values.
    get_usage_limits: Converts AgentBudget presets to PydanticAI UsageLimits
        with optional per-field overrides.
    PipelineBudgetTracker: Immutable accumulator that tracks total token
        usage across all agents in a pipeline run and raises
        BudgetExceededError when the pipeline cap is exceeded.
    AgentUsageRecord: Frozen per-agent token usage record for audit.
    BudgetExceededError: Raised when cumulative usage exceeds pipeline limit.

Design:
    - All dataclasses are frozen (immutable) per project conventions.
    - record_usage returns a NEW tracker -- original is never mutated.
    - records stored as tuple (immutable sequence) not list.
    - Threat model T-02-01 (DoS): UsageLimits on every agent call + pipeline cap.
    - Threat model T-02-02 (Tampering): Frozen dataclasses prevent runtime mutation.
    - Threat model T-02-03 (Repudiation): AgentUsageRecord provides audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.models import MODEL_BUDGETS, ModelTier


class BudgetExceededError(Exception):
    """Raised when cumulative pipeline token usage exceeds the configured limit.

    Attributes:
        agent_name: Name of the agent whose usage triggered the limit.
        tokens_used: Total tokens used at the time of the error.
        tokens_limit: The configured pipeline token limit.
    """

    def __init__(self, agent_name: str, tokens_used: int, tokens_limit: int) -> None:
        self.agent_name = agent_name
        self.tokens_used = tokens_used
        self.tokens_limit = tokens_limit
        super().__init__(
            f"Pipeline budget exceeded by agent '{agent_name}': "
            f"{tokens_used:,} tokens used, limit is {tokens_limit:,}"
        )


def create_agent(
    model_tier: ModelTier,
    output_type: type[BaseModel],
    system_prompt: str,
    **kwargs: Any,
) -> Agent:
    """Create a PydanticAI Agent with model-tier routing.

    Centralizes agent creation so every agent goes through a single path
    that resolves model strings from the ModelTier enum.

    Args:
        model_tier: Which Claude model tier to use (EXTRACTION/ANALYSIS/REASONING).
        output_type: Pydantic BaseModel subclass for validated output.
        system_prompt: System prompt string for the agent.
        **kwargs: Additional keyword arguments forwarded to Agent().

    Returns:
        Configured PydanticAI Agent instance.
    """
    return Agent(
        model_tier.value,
        output_type=output_type,
        system_prompt=system_prompt,
        **kwargs,
    )


def get_usage_limits(
    model_tier: ModelTier,
    *,
    input_override: int | None = None,
    output_override: int | None = None,
    total_override: int | None = None,
) -> UsageLimits:
    """Convert a ModelTier's AgentBudget preset to PydanticAI UsageLimits.

    Looks up the budget for the given tier and creates a UsageLimits
    instance. Individual limits can be overridden without affecting
    the other fields.

    Args:
        model_tier: Which tier to look up budget defaults for.
        input_override: Override input token limit (None = use default).
        output_override: Override output token limit (None = use default).
        total_override: Override total token limit (None = use default).

    Returns:
        UsageLimits configured for the tier with any overrides applied.
    """
    budget = MODEL_BUDGETS[model_tier]
    return UsageLimits(
        input_tokens_limit=input_override
        if input_override is not None
        else budget.input_tokens_limit,
        output_tokens_limit=output_override
        if output_override is not None
        else budget.output_tokens_limit,
        total_tokens_limit=total_override
        if total_override is not None
        else budget.total_tokens_limit,
    )


@dataclass(frozen=True)
class AgentUsageRecord:
    """Frozen record of a single agent's token usage within a pipeline run.

    Provides audit trail per threat model T-02-03 (Repudiation).
    """

    agent_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class PipelineBudgetTracker:
    """Immutable accumulator for pipeline-wide token budget tracking.

    Each call to record_usage returns a NEW tracker instance with the
    updated records -- the original is never mutated. Records are stored
    as a tuple (immutable sequence).

    Raises BudgetExceededError if cumulative usage exceeds total_limit.

    Attributes:
        total_limit: Maximum total tokens allowed across all agents.
        records: Immutable sequence of AgentUsageRecord entries.
    """

    total_limit: int = 500_000
    records: tuple[AgentUsageRecord, ...] = field(default_factory=tuple)

    @property
    def total_used(self) -> int:
        """Sum of total_tokens across all recorded agent runs."""
        return sum(record.total_tokens for record in self.records)

    @property
    def remaining_budget(self) -> int:
        """Tokens remaining before hitting the pipeline limit."""
        return self.total_limit - self.total_used

    def record_usage(
        self,
        agent_name: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
    ) -> PipelineBudgetTracker:
        """Record an agent's token usage, returning a new tracker.

        The original tracker is NOT modified (frozen dataclass with
        immutable tuple records).

        Args:
            agent_name: Identifier for the agent that consumed tokens.
            input_tokens: Number of input tokens consumed.
            output_tokens: Number of output tokens consumed.
            total_tokens: Total tokens consumed (input + output + overhead).

        Returns:
            New PipelineBudgetTracker with the usage recorded.

        Raises:
            BudgetExceededError: If cumulative usage exceeds total_limit.
        """
        new_record = AgentUsageRecord(agent_name, input_tokens, output_tokens, total_tokens)
        new_records = self.records + (new_record,)
        new_tracker = PipelineBudgetTracker(
            total_limit=self.total_limit,
            records=new_records,
        )
        if new_tracker.total_used > self.total_limit:
            raise BudgetExceededError(agent_name, new_tracker.total_used, self.total_limit)
        return new_tracker

    def usage_summary(self) -> dict[str, Any]:
        """Return a summary dict of pipeline token usage.

        Returns:
            Dict with keys: total_used, total_limit, remaining,
            breakdown_by_agent (agent_name -> total_tokens).
        """
        return {
            "total_used": self.total_used,
            "total_limit": self.total_limit,
            "remaining": self.remaining_budget,
            "breakdown_by_agent": {
                record.agent_name: record.total_tokens for record in self.records
            },
        }
