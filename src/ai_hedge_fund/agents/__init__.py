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
    research_agent: Pre-configured Sonnet research agent with tool wrappers
    get_research_limits: UsageLimits for research agent (ANALYSIS tier)
    ResearchDeps: Immutable dependency container for the research agent
    signal_agent: Pre-configured Sonnet signal agent (thesis -> SignalOutput)
    get_signal_limits: UsageLimits for signal agent (ANALYSIS tier)
    fundamental_agent / get_fundamental_limits: Phase-4 fundamental analyst
    sentiment_agent / get_sentiment_limits: Phase-4 sentiment analyst
    technical_agent / get_technical_limits: Phase-4 technical analyst
    manager_agent / get_manager_limits: Phase-4 research manager (Opus)
    format_analyst_reports: Helper for converting analyst report dicts to a
        readable string suitable for the manager's user prompt.
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
    DEBATE_SYNTHESIS_SYSTEM_PROMPT,
    EVIDENCE_WEIGHT,
    LOGIC_WEIGHT,
    RISK_WEIGHT,
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
    RISK_MANAGER_SYSTEM_PROMPT,
    RationaleOnly,
    format_risk_context_for_rationale,
    get_risk_manager_limits,
    risk_manager_agent,
)
from ai_hedge_fund.agents.sentiment import get_sentiment_limits, sentiment_agent
from ai_hedge_fund.agents.signal import get_signal_limits, signal_agent
from ai_hedge_fund.agents.technical import get_technical_limits, technical_agent

__all__ = [
    "AgentUsageRecord",
    "BudgetExceededError",
    "DEBATE_SYNTHESIS_SYSTEM_PROMPT",
    "EVIDENCE_WEIGHT",
    "LOGIC_WEIGHT",
    "PipelineBudgetTracker",
    "RISK_MANAGER_SYSTEM_PROMPT",
    "RISK_WEIGHT",
    "RationaleOnly",
    "ResearchDeps",
    "analysis_agent",
    "bear_agent",
    "bull_agent",
    "compute_quality_score",
    "create_agent",
    "debate_synthesis_agent",
    "extraction_agent",
    "final_arguments_agent",
    "format_analyst_evidence",
    "format_analyst_reports",
    "format_bull_case_for_bear",
    "format_debate_for_final",
    "format_debate_for_rebuttal",
    "format_debate_for_synthesis",
    "format_risk_context_for_rationale",
    "fundamental_agent",
    "get_analysis_limits",
    "get_bear_limits",
    "get_bull_limits",
    "get_debate_synthesis_limits",
    "get_extraction_limits",
    "get_final_arguments_limits",
    "get_fundamental_limits",
    "get_manager_limits",
    "get_rebuttal_limits",
    "get_research_limits",
    "get_risk_manager_limits",
    "get_sentiment_limits",
    "get_signal_limits",
    "get_technical_limits",
    "get_usage_limits",
    "manager_agent",
    "rebuttal_agent",
    "research_agent",
    "risk_manager_agent",
    "sentiment_agent",
    "signal_agent",
    "technical_agent",
]
