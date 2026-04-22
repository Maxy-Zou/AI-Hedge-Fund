"""Risk Manager agent — rationale-only PydanticAI agent (RISK-01).

The agent receives a PRE-COMPUTED deterministic risk assessment (status +
violation, if any) in its user prompt and produces a short human-readable
explanation. The LLM does NOT decide anything — deterministic Python in
``ai_hedge_fund.risk.checks``, ``ai_hedge_fund.risk.correlation``, and
``ai_hedge_fund.risk.drawdown`` produces the :class:`Violation`; plan
06-05's ``risk_manager_node`` assembles the final
:class:`ai_hedge_fund.schemas.risk.RiskAssessment` with a Python-authored
``status`` after this agent returns (Pattern 2 from 06-RESEARCH.md; Pitfall
1 prevention).

Threat mitigations:
    T-06-02:  Veto bypass -- the output schema is :class:`RationaleOnly`
              (a single ``rationale: str`` field), so a jailbroken LLM
              CANNOT produce an APPROVED status for a violating signal.
              The decision is schema-unreachable for the model.
    T-06-02b: Sycophantic rationale / prompt-injected decision making --
              system prompt uses "explain" exclusively, never "decide" or
              "judge". The forbidden-verb absence is enforced by
              ``tests/risk/test_risk_manager_agent.py``.
    T-05-13-analog: Rationale DoS -- ``get_risk_manager_limits`` applies
              ``output_override=4_000`` and :class:`RationaleOnly` caps the
              string at ``max_length=2000``; two independent bounds.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import PortfolioSnapshot
from ai_hedge_fund.schemas.risk import Violation


class RationaleOnly(BaseModel):
    """The agent's only job: produce a rationale string. Nothing else.

    The ``status``, ``constraint_violated``, ``observed``, and ``limit``
    fields on :class:`RiskAssessment` are set by deterministic Python in
    ``risk_manager_node`` (plan 06-05) AFTER this agent returns. If you
    are tempted to add a status field here, stop -- that violates RISK-01.
    """

    rationale: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "One-paragraph human-readable explanation of the risk "
            "assessment. Must reference the ticker, the observed vs "
            "limit values (when a violation is present), and the "
            "portfolio context. Advisory only -- does not affect the "
            "APPROVED/VETOED outcome."
        ),
    )


RISK_MANAGER_SYSTEM_PROMPT = (
    "You are the Risk Manager rationale writer. A deterministic Python "
    "function has ALREADY computed whether a proposed trade is APPROVED "
    "or VETOED and (if vetoed) which named constraint was violated. "
    "Your ONLY job is to EXPLAIN the outcome in one paragraph.\n"
    "\n"
    "Your input contains:\n"
    "  - the proposed thesis (ticker, conviction, direction)\n"
    "  - the deterministic status: APPROVED or VETOED\n"
    "  - when VETOED: the constraint_violated name, observed value, and limit\n"
    "  - a snapshot of the current paper portfolio\n"
    "  - the risk policy the decision was measured against\n"
    "\n"
    "STRICT RULES:\n"
    "1. You DO NOT author the outcome. You EXPLAIN the outcome already "
    "computed by Python.\n"
    "2. When the status is VETOED, name the specific constraint, state "
    "the observed value and the limit, and cite which portfolio context "
    "or market data caused the breach.\n"
    "3. When the status is APPROVED, state that all checks passed "
    "(position size, sector concentration, correlation, drawdown) and "
    "briefly note the slack to each limit.\n"
    "4. Never recommend raising or lowering the limits -- those are "
    "human-editable policy in config/risk_policy.yaml.\n"
    "5. Output a single RationaleOnly object with one 'rationale' field. "
    "Target length: 2-5 sentences. No headings. No bullet lists.\n"
)


risk_manager_agent: Agent[None, RationaleOnly] = Agent(
    ModelTier.REASONING.value,
    output_type=RationaleOnly,
    system_prompt=RISK_MANAGER_SYSTEM_PROMPT,
    retries=2,
)


def get_risk_manager_limits() -> UsageLimits:
    """Return REASONING-tier limits with output capped at 4,000 tokens.

    The rationale is short (2-5 sentences), so the output cap is much
    tighter than the REASONING default of 16,000. Input cap is the full
    REASONING budget so the agent can see a full policy + portfolio dump
    without truncation.
    """
    return get_usage_limits(ModelTier.REASONING, output_override=4_000)


def format_risk_context_for_rationale(
    thesis: dict,
    status: str,
    violation: Violation | None,
    portfolio: PortfolioSnapshot,
    policy: RiskPolicy,
) -> str:
    """Build a deterministic 5-section context string for the agent's user prompt.

    Sections are separated by ``\\n\\n---\\n\\n`` and labelled
    ``THESIS``, ``DETERMINISTIC STATUS``, ``VIOLATION``, ``PORTFOLIO``,
    ``POLICY``. Pure function -- no I/O, no logging. Determinism matters:
    the rationale prompt must be reproducible across runs for audit.
    """
    thesis_section = f"THESIS:\n{json.dumps(thesis, indent=2, default=str)}"
    status_section = f"DETERMINISTIC STATUS: {status}"
    if violation is None:
        violation_section = "VIOLATION: none (all checks passed)"
    else:
        violation_section = (
            "VIOLATION:\n"
            f"  constraint: {violation.name}\n"
            f"  observed: {violation.observed}\n"
            f"  limit: {violation.limit}"
        )
    portfolio_section = f"PORTFOLIO:\n{json.dumps(portfolio.model_dump(), indent=2, default=str)}"
    policy_section = f"POLICY:\n{json.dumps(policy.model_dump(), indent=2, default=str)}"
    return "\n\n---\n\n".join(
        [
            thesis_section,
            status_section,
            violation_section,
            portfolio_section,
            policy_section,
        ]
    )
