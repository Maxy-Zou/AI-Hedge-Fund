"""Tests for the Risk Manager PydanticAI agent (plan 06-04).

Covers 11 behaviours proving the agent is RATIONALE-ONLY and cannot
author the APPROVED/VETOED decision:

    1.  ``risk_manager_agent`` is a :class:`pydantic_ai.Agent` instance.
    2.  ``risk_manager_agent.output_type`` is :class:`RationaleOnly`.
    3.  ``RationaleOnly`` validates non-empty strings; empty raises.
    4.  Agent has zero registered tools (per
        :mod:`tests/unit/test_manager_agent.py::test_agent_no_tools`).
    5.  ``get_risk_manager_limits`` applies ``output_override=4_000``.
    6.  ``get_risk_manager_limits`` uses REASONING tier budget.
    7.  ``RISK_MANAGER_SYSTEM_PROMPT`` mentions the word "explain".
    8.  System prompt lacks forbidden decision verbs (Pitfall 1).
    9.  ``format_risk_context_for_rationale`` on APPROVED status produces
        a string that names the ticker and the APPROVED status.
    10. On VETOED status the formatter includes the constraint name,
        observed value, and limit in the context string.
    11. TestModel stub end-to-end proves the agent wires correctly to the
        PydanticAI runtime without a real LLM call.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pytest
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.risk_manager import (
    RISK_MANAGER_SYSTEM_PROMPT,
    RationaleOnly,
    format_risk_context_for_rationale,
    get_risk_manager_limits,
    risk_manager_agent,
)
from ai_hedge_fund.models import MODEL_BUDGETS, ModelTier
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import PortfolioSnapshot, PortfolioSnapshotPosition
from ai_hedge_fund.schemas.risk import Violation


@pytest.fixture()
def portfolio_fixture() -> PortfolioSnapshot:
    positions = [
        PortfolioSnapshotPosition(
            ticker="AAPL",
            sector="Technology",
            quantity=10.0,
            cost_basis_cents=15_000_00,
            current_value_cents=20_000_00,
        ),
        PortfolioSnapshotPosition(
            ticker="JNJ",
            sector="Healthcare",
            quantity=10.0,
            cost_basis_cents=15_000_00,
            current_value_cents=18_000_00,
        ),
    ]
    return PortfolioSnapshot(
        as_of_date="2025-04-01",
        positions=positions,
        total_value_cents=38_000_00,
    )


@pytest.fixture()
def policy_fixture() -> RiskPolicy:
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.80,
        max_projected_drawdown_pct=25.0,
    )


# ---------- Agent wiring ----------


def test_agent_is_pydantic_ai_agent() -> None:
    assert isinstance(risk_manager_agent, Agent)


def test_agent_output_type_is_rationale_only() -> None:
    assert risk_manager_agent._output_type is RationaleOnly


def test_rationale_only_rejects_empty_string() -> None:
    RationaleOnly(rationale="ok")
    with pytest.raises(ValidationError):
        RationaleOnly(rationale="")


def test_agent_has_no_tools() -> None:
    """Mirrors ``tests/unit/test_manager_agent.py::test_agent_no_tools``."""
    tools = risk_manager_agent._function_toolset.tools
    assert len(tools) == 0


# ---------- Limits ----------


def test_get_risk_manager_limits_applies_output_override() -> None:
    limits = get_risk_manager_limits()
    assert isinstance(limits, UsageLimits)
    assert limits.output_tokens_limit == 4_000


def test_get_risk_manager_limits_uses_reasoning_tier() -> None:
    limits = get_risk_manager_limits()
    assert limits.input_tokens_limit == MODEL_BUDGETS[ModelTier.REASONING].input_tokens_limit


# ---------- System prompt ----------


def test_system_prompt_uses_explain_verb() -> None:
    assert "explain" in RISK_MANAGER_SYSTEM_PROMPT.lower()


def test_system_prompt_lacks_forbidden_decision_verbs() -> None:
    """Pitfall 1: the agent MUST NOT be told to decide / judge / veto."""
    prompt_lower = RISK_MANAGER_SYSTEM_PROMPT.lower()
    forbidden = ["you decide", "you must decide", "you judge", "your veto"]
    assert not any(term in prompt_lower for term in forbidden)


# ---------- Format helper ----------


def test_format_approved_context_includes_ticker_and_status(
    portfolio_fixture: PortfolioSnapshot, policy_fixture: RiskPolicy
) -> None:
    thesis = {
        "ticker": "MSFT",
        "direction": "long",
        "conviction": "medium",
        "confidence": 72,
    }
    context = format_risk_context_for_rationale(
        thesis=thesis,
        status="APPROVED",
        violation=None,
        portfolio=portfolio_fixture,
        policy=policy_fixture,
    )
    assert "MSFT" in context
    assert "APPROVED" in context
    assert "VIOLATION: none" in context


def test_format_vetoed_context_includes_constraint_observed_and_limit(
    portfolio_fixture: PortfolioSnapshot, policy_fixture: RiskPolicy
) -> None:
    thesis = {"ticker": "XOM", "direction": "long", "conviction": "high"}
    violation = Violation(name="max_single_position_pct", observed=15.0, limit=10.0)
    context = format_risk_context_for_rationale(
        thesis=thesis,
        status="VETOED",
        violation=violation,
        portfolio=portfolio_fixture,
        policy=policy_fixture,
    )
    assert "VETOED" in context
    assert "max_single_position_pct" in context
    assert "15.0" in context
    assert "10.0" in context


# ---------- End-to-end with TestModel stub ----------


def test_agent_runs_with_test_model_stub() -> None:
    """Stub the model so no real LLM call happens; assert the wiring works."""
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": "stubbed rationale"})
    ):
        result = risk_manager_agent.run_sync("explain this: APPROVED")

    assert isinstance(result.output, RationaleOnly)
    assert result.output.rationale == "stubbed rationale"
