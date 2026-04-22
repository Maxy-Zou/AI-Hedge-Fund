"""Tests for the self-critique PydanticAI agent (Plan 07-04 Task 2).

Mirrors ``tests/risk/test_risk_manager_agent.py``: the agent is
RATIONALE-ONLY and cannot author the new_confidence number (Pattern 2).

The invariants enforced here:
    1. :class:`RationaleOnly` has exactly ONE field, ``rationale: str``
       (T-07-30: the LLM CANNOT emit a numeric confidence).
    2. :class:`RationaleOnly` bounds: ``min_length=1``, ``max_length=2000``
       (T-05-13-analog DoS guard).
    3. Agent wires to :class:`ModelTier.REASONING` with ``retries=2`` and
       ``output_type=RationaleOnly``. Assertion shape mirrors
       ``tests/risk/test_risk_manager_agent.py``.
    4. Forbidden-verb invariant (T-07-31, analog of T-06-02b): system
       prompt contains ``EXPLAIN`` and no decision-verb
       (decide/decides/judge/judges/determine/determines/rule/rules/
       verdict/verdicts). Word-boundary regex.
    5. :func:`get_self_critique_limits` applies ``output_override=4_000``.
    6. :class:`TestModel` stub end-to-end: agent wires correctly to the
       PydanticAI runtime without a real LLM call.
"""

from __future__ import annotations

import asyncio
import os
import re

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pytest
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.self_critique import (
    SELF_CRITIQUE_SYSTEM_PROMPT,
    RationaleOnly,
    get_self_critique_limits,
    self_critique_agent,
)
from ai_hedge_fund.models import MODEL_BUDGETS, ModelTier


# ---------- Schema contract (T-07-30 defense-in-depth) ----------


def test_rationale_only_has_single_field() -> None:
    """RationaleOnly has EXACTLY one field: rationale. No number reachable."""
    assert list(RationaleOnly.model_fields) == ["rationale"]


def test_rationale_only_forbids_new_confidence() -> None:
    """Belt-and-braces: no confidence/number field is reachable via schema."""
    fields = set(RationaleOnly.model_fields)
    forbidden = {"new_confidence", "confidence", "number", "score"}
    assert fields.isdisjoint(forbidden)


def test_rationale_only_accepts_non_empty() -> None:
    RationaleOnly(rationale="x")


def test_rationale_only_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        RationaleOnly(rationale="")


def test_rationale_only_rejects_over_max_length() -> None:
    with pytest.raises(ValidationError):
        RationaleOnly(rationale="a" * 2001)


# ---------- Agent wiring (copy shape from tests/risk/test_risk_manager_agent.py) ----------


def test_agent_is_pydantic_ai_agent() -> None:
    assert isinstance(self_critique_agent, Agent)


def test_agent_output_type_is_rationale_only() -> None:
    # Mirrors tests/risk/test_risk_manager_agent.py::test_agent_output_type_is_rationale_only.
    assert self_critique_agent._output_type is RationaleOnly


def test_agent_has_no_tools() -> None:
    """Mirrors the risk-agent tool-count invariant."""
    tools = self_critique_agent._function_toolset.tools
    assert len(tools) == 0


# ---------- System prompt: forbidden-verb invariant (T-07-31 / T-06-02b analog) ----------


def test_system_prompt_uses_explain_verb() -> None:
    # EXPLAIN (case-insensitive) must appear; the agent's whole job is to
    # EXPLAIN the deterministic number, not DECIDE it.
    assert "explain" in SELF_CRITIQUE_SYSTEM_PROMPT.lower()


def test_system_prompt_forbidden_verbs_absent() -> None:
    """Word-boundary regex rejects any decision-verb tokens in the prompt."""
    lowered = SELF_CRITIQUE_SYSTEM_PROMPT.lower()
    forbidden = [
        "decide",
        "decides",
        "judge",
        "judges",
        "determine",
        "determines",
        "rule",
        "rules",
        "verdict",
        "verdicts",
    ]
    for verb in forbidden:
        assert not re.search(rf"\b{verb}\b", lowered), (
            f"Forbidden verb {verb!r} appeared in self-critique system prompt"
        )


# ---------- Usage limits ----------


def test_self_critique_limits_applies_output_override() -> None:
    limits = get_self_critique_limits()
    assert isinstance(limits, UsageLimits)
    assert limits.output_tokens_limit == 4_000


def test_self_critique_limits_uses_reasoning_tier() -> None:
    limits = get_self_critique_limits()
    assert (
        limits.input_tokens_limit
        == MODEL_BUDGETS[ModelTier.REASONING].input_tokens_limit
    )


# ---------- End-to-end with TestModel stub ----------


def test_agent_runs_with_test_model_stub() -> None:
    """Stub the model so no real LLM call happens; wiring proven."""
    stub = "stubbed self-critique rationale"
    with self_critique_agent.override(
        model=TestModel(custom_output_args={"rationale": stub})
    ):
        result = asyncio.run(self_critique_agent.run("test prompt"))

    assert isinstance(result.output, RationaleOnly)
    assert result.output.rationale == stub
