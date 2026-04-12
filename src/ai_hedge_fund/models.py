"""Claude model tier definitions and per-agent token budget configuration.

Dual-model routing: each agent is assigned a model tier based on task
complexity. Budget presets enforce token caps per agent run.

Model tiers:
    EXTRACTION -- Claude Haiku: fast, cheap, sufficient for data extraction
    ANALYSIS   -- Claude Sonnet: best balance for analytical work
    REASONING  -- Claude Opus: deepest reasoning for adversarial debate
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelTier(Enum):
    """Claude model tiers for dual-model routing.

    Values use PydanticAI model string format: 'provider:model-name'.
    """

    EXTRACTION = "anthropic:claude-haiku-4-5"
    ANALYSIS = "anthropic:claude-sonnet-4-6"
    REASONING = "anthropic:claude-opus-4-6"


@dataclass(frozen=True)
class AgentBudget:
    """Immutable token budget configuration per agent.

    Frozen dataclass ensures budgets cannot be accidentally mutated
    at runtime. Use MODEL_BUDGETS to look up presets by tier.
    """

    input_tokens_limit: int
    output_tokens_limit: int
    total_tokens_limit: int


# Budget presets by model tier (conservative defaults).
# These map to PydanticAI UsageLimits at agent invocation time.
MODEL_BUDGETS: dict[ModelTier, AgentBudget] = {
    ModelTier.EXTRACTION: AgentBudget(
        input_tokens_limit=20_000,
        output_tokens_limit=2_000,
        total_tokens_limit=22_000,
    ),
    ModelTier.ANALYSIS: AgentBudget(
        input_tokens_limit=50_000,
        output_tokens_limit=8_000,
        total_tokens_limit=58_000,
    ),
    ModelTier.REASONING: AgentBudget(
        input_tokens_limit=100_000,
        output_tokens_limit=16_000,
        total_tokens_limit=116_000,
    ),
}
