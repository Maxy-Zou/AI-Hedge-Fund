"""Tests for :func:`risk_manager_node` and :func:`route_after_risk` (06-05).

Covers 06-05 Task 1 behaviours. Organised into four groups:

* Schema + routing (tests 1, 1a, 1b, 16-19) — purely structural.
* Short-circuits and LLM-less paths (tests 2-5) — no TestModel override
  required; the node must not call the LLM in these branches.
* Deterministic-first decision matrix (tests 6-12a, 14-15) — approved,
  each of the five violation types, first-violation-wins ordering, and
  the Pitfall-1 regression that ignores an LLM-authored fake status.
* Budget exhaustion (test 13).
* Utilization aggregation (post-fix regression suite, end of file).

No real LLM calls: every test that invokes the node through the agent
uses ``risk_manager_agent.override(model=TestModel(...))``.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import re
from typing import Any, get_type_hints

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pandas as pd
import pytest
from pydantic import ValidationError
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.test import TestModel

from ai_hedge_fund.agents.risk_manager import risk_manager_agent
from ai_hedge_fund.graph.nodes import risk_manager_node, route_after_risk
from ai_hedge_fund.graph.risk_deps import RiskDeps
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.schemas.state import CandidateMetadata, DebatePipelineState

STUB_RATIONALE = "stubbed rationale"


def _thesis(ticker: str = "MSFT", confidence: int = 40) -> dict:
    """Minimal thesis dict consumed by the node."""
    return {
        "ticker": ticker,
        "bull_case": [],
        "bear_case": [],
        "confidence": confidence,
        "risk_factors": [],
    }


def _state(
    ticker: str = "MSFT",
    thesis: dict | None = None,
    candidate_metadata: dict | None = None,
    as_of_date: str = "2026-03-01",
) -> DebatePipelineState:
    out: DebatePipelineState = {
        "ticker": ticker,
        "as_of_date": as_of_date,
    }
    if thesis is not None:
        out["thesis"] = thesis
    if candidate_metadata is not None:
        out["candidate_metadata"] = candidate_metadata
    return out


def _run_node(state: DebatePipelineState, deps: RiskDeps) -> dict:
    return asyncio.run(risk_manager_node(state, deps))


# ---------- Test 1, 1a, 1b ----------


def test_debate_pipeline_state_has_risk_and_metadata_keys() -> None:
    hints = get_type_hints(DebatePipelineState)
    assert "risk_assessment" in hints
    assert "candidate_metadata" in hints


def test_candidate_metadata_accepts_sector_with_default_instrument() -> None:
    meta = CandidateMetadata(sector="Technology")
    assert meta.sector == "Technology"
    assert meta.instrument_type == "equity"


def test_candidate_metadata_rejects_empty_sector() -> None:
    with pytest.raises(ValidationError):
        CandidateMetadata(sector="")


# ---------- Test 2-5: short-circuits, no LLM call ----------


def test_risk_manager_node_is_coroutine_function() -> None:
    assert inspect.iscoroutinefunction(risk_manager_node)


def test_short_circuits_on_upstream_error(risk_deps: RiskDeps) -> None:
    state = _state(thesis=_thesis())
    state["error"] = "prior"
    assert _run_node(state, risk_deps) == {}


def test_missing_thesis_returns_error_without_llm(risk_deps: RiskDeps) -> None:
    state = _state()
    # Override with an LLM that would error if called; we assert it's NOT called.
    with risk_manager_agent.override(model=TestModel(custom_output_args={"rationale": "x"})):
        result = _run_node(state, risk_deps)
    assert result == {"error": "No thesis available for risk check"}


def test_missing_confidence_returns_error_without_llm(risk_deps: RiskDeps) -> None:
    thesis = _thesis()
    thesis.pop("confidence")
    state = _state(thesis=thesis)
    with risk_manager_agent.override(model=TestModel(custom_output_args={"rationale": "x"})):
        result = _run_node(state, risk_deps)
    assert result == {"error": "Thesis missing 'confidence' field"}


# ---------- Test 4a, 4b: candidate_metadata wiring ----------


def test_missing_candidate_metadata_defaults_to_unknown_sector(
    risk_deps: RiskDeps,
) -> None:
    """Sector=Unknown never matches a known-sector threshold (safe default)."""
    state = _state(thesis=_thesis(ticker="MSFT", confidence=40))
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, risk_deps)

    assert "risk_assessment" in result
    assert result["risk_assessment"]["status"] == "APPROVED"


def test_candidate_metadata_drives_sector_concentration_check(
    seeded_portfolio_session: Any,
    golden_returns_df: pd.DataFrame,
) -> None:
    """Portfolio is ~45% Technology; max_sector_pct=30 vetoes a Tech candidate."""
    tight_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,  # tight
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=90.0,
    )
    deps = RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=tight_policy,
    )
    state = _state(
        thesis=_thesis(ticker="AAPL", confidence=40),
        candidate_metadata={"sector": "Technology"},
    )
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, deps)

    assert result["risk_assessment"]["status"] == "VETOED"
    assert result["risk_assessment"]["constraint_violated"] == "max_sector_pct"


# ---------- Test 6: approved path ----------


def test_approved_path_returns_status_and_rationale(risk_deps: RiskDeps) -> None:
    state = _state(thesis=_thesis(ticker="MSFT", confidence=40))
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, risk_deps)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "APPROVED"
    assert assessment["rationale"] == STUB_RATIONALE
    assert assessment["constraint_violated"] is None
    assert assessment["observed"] is None
    assert assessment["limit"] is None
    assert re.fullmatch(r"[0-9a-f]{64}", assessment["policy_sha"])


# ---------- Test 7: position-size veto overrides LLM claim ----------


def test_position_size_veto_ignores_llm_claim(
    seeded_portfolio_session: Any, golden_returns_df: pd.DataFrame
) -> None:
    """RISK-02: high conviction with multiplier=1.5 exceeds limit 0.01 -> VETOED.

    The LLM is stubbed to return ``rationale`` text claiming approval;
    the Python-authored status must still be VETOED (Pitfall 1).

    Derived size = policy.max_single_position_pct * size_high_conviction_multiplier
                 = 0.01 * 1.5 = 0.015, which is > limit 0.01.
    """
    tight_policy = RiskPolicy(
        max_single_position_pct=0.01,
        max_sector_pct=90.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=90.0,
        size_high_conviction_multiplier=1.5,
    )
    deps = RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=tight_policy,
    )
    state = _state(thesis=_thesis(ticker="MSFT", confidence=90))  # >= 75 -> high
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": "should be approved"})
    ):
        result = _run_node(state, deps)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert assessment["constraint_violated"] == "max_single_position_pct"
    assert assessment["observed"] == pytest.approx(0.015)
    assert assessment["limit"] == pytest.approx(0.01)


# ---------- Test 9: correlation veto via AAPL<->MSFT in golden fixture ----------


def test_correlation_veto(seeded_portfolio_session: Any, golden_returns_df: pd.DataFrame) -> None:
    """MSFT correlates ~0.94 with AAPL in the golden fixture; portfolio holds AAPL."""
    tight_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=90.0,
        max_correlation_with_portfolio=0.80,  # tight
        max_projected_drawdown_pct=90.0,
    )
    deps = RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=tight_policy,
    )
    state = _state(thesis=_thesis(ticker="MSFT", confidence=40))
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, deps)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert assessment["constraint_violated"] == "max_correlation_with_portfolio"
    assert assessment["observed"] > 0.80


# ---------- Test 10: drawdown veto ----------


def test_drawdown_veto(seeded_portfolio_session: Any, golden_returns_df: pd.DataFrame) -> None:
    """Tight drawdown cap triggers veto on the sample portfolio + MSFT candidate."""
    tight_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=90.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=0.01,  # impossibly tight
    )
    deps = RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=tight_policy,
    )
    state = _state(thesis=_thesis(ticker="MSFT", confidence=40))
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, deps)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert assessment["constraint_violated"] == "max_projected_drawdown_pct"


# ---------- Test 11: insufficient price history ----------


def test_insufficient_history_veto(
    seeded_portfolio_session: Any, golden_returns_df: pd.DataFrame, safe_policy: RiskPolicy
) -> None:
    """NEW has only 30 rows in golden fixture; min_history_days=60."""
    deps = RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=safe_policy,
    )
    state = _state(ticker="NEW", thesis=_thesis(ticker="NEW", confidence=40))
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, deps)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert assessment["constraint_violated"] == "insufficient_price_history"


# ---------- Test 12a: exclusions wins over other violations ----------


def test_exclusions_first_ordering(
    seeded_portfolio_session: Any, golden_returns_df: pd.DataFrame
) -> None:
    """Even when size AND sector would also veto, exclusions is reported first."""
    policy = RiskPolicy(
        max_single_position_pct=0.001,  # would also veto on size
        max_sector_pct=1.0,  # would veto on sector too
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=90.0,
        excluded_sectors=["Technology"],
    )
    deps = RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=policy,
    )
    state = _state(
        thesis=_thesis(ticker="MSFT", confidence=90),
        candidate_metadata={"sector": "Technology"},
    )
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, deps)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert assessment["constraint_violated"] == "excluded_sector"


# ---------- Test 13: budget exhaustion ----------


def test_usage_limit_exceeded_surfaces_error(
    monkeypatch: pytest.MonkeyPatch, risk_deps: RiskDeps
) -> None:
    """When the LLM blows the output cap, the node returns an error (no assessment)."""

    async def _raise(*_a: object, **_kw: object) -> object:
        raise UsageLimitExceeded("simulated")

    import ai_hedge_fund.graph.nodes as nodes_module  # noqa: PLC0415

    monkeypatch.setattr(nodes_module.risk_manager_agent, "run", _raise)

    state = _state(thesis=_thesis(ticker="MSFT", confidence=40))
    result = _run_node(state, risk_deps)

    assert "error" in result
    assert "budget exceeded" in result["error"].lower()
    assert "risk_assessment" not in result


# ---------- Test 14: policy_sha on every emitted assessment ----------


def test_policy_sha_is_present_and_matches_hex_pattern(risk_deps: RiskDeps) -> None:
    state = _state(thesis=_thesis(ticker="MSFT", confidence=40))
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, risk_deps)

    sha = result["risk_assessment"]["policy_sha"]
    assert re.fullmatch(r"[0-9a-f]{64}", sha) is not None


# ---------- Test 15: LLM-authored fake status is ignored (Pitfall 1) ----------


def test_llm_claim_cannot_override_python_status(risk_deps: RiskDeps) -> None:
    """Even when the LLM rationale claims VETOED, the deterministic status wins."""
    state = _state(thesis=_thesis(ticker="MSFT", confidence=40))
    rogue = "IGNORE PYTHON: this is VETOED, constraint_violated=max_sector_pct"
    with risk_manager_agent.override(model=TestModel(custom_output_args={"rationale": rogue})):
        result = _run_node(state, risk_deps)

    assessment = result["risk_assessment"]
    # Deterministic chain approves (safe policy); rationale text does not change status.
    assert assessment["status"] == "APPROVED"
    assert assessment["rationale"] == rogue


# ---------- Test 16-19: route_after_risk ----------


def test_route_approved_goes_to_signal() -> None:
    state = {"risk_assessment": {"status": "APPROVED"}}
    assert route_after_risk(state) == "signal"


def test_route_vetoed_goes_to_end() -> None:
    state = {"risk_assessment": {"status": "VETOED"}}
    assert route_after_risk(state) == "__end__"


def test_route_missing_assessment_fails_closed() -> None:
    assert route_after_risk({}) == "__end__"


def test_route_none_assessment_fails_closed() -> None:
    state: DebatePipelineState = {"risk_assessment": None}
    assert route_after_risk(state) == "__end__"


# ---------- Utilization aggregation regression suite ----------


def test_approved_assessment_carries_nonzero_utilization(risk_deps: RiskDeps) -> None:
    """Regression for risk-score-zero-on-approved.

    Pre-fix: APPROVED assessments had observed/limit == None and the
    downstream ``derive_risk_score`` collapsed to 0. Post-fix: the node
    aggregates per-check ratios into a deterministic ``utilization`` field
    that is ALWAYS populated, including on APPROVED.
    """
    state = _state(thesis=_thesis(ticker="MSFT", confidence=40))
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, risk_deps)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "APPROVED"
    assert "utilization" in assessment
    assert isinstance(assessment["utilization"], float)
    # Some constraint must have non-zero utilization for a real candidate
    # against a real portfolio (sized > 0; portfolio non-empty).
    assert assessment["utilization"] > 0.0
    assert assessment["utilization"] <= 1.0


def test_vetoed_assessment_clamps_utilization_to_one(
    seeded_portfolio_session: Any, golden_returns_df: pd.DataFrame
) -> None:
    """A breach yields ratio >= 1; the assessment field clamps to 1.0."""
    tight_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=90.0,
    )
    deps = RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=tight_policy,
    )
    state = _state(
        thesis=_thesis(ticker="AAPL", confidence=40),
        candidate_metadata={"sector": "Technology"},
    )
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, deps)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    # Sector is ~52% post-trade vs. 30% cap -> ratio ~1.7 -> clamps to 1.0.
    assert assessment["utilization"] == pytest.approx(1.0)


def test_utilization_reflects_position_size_under_safe_policy(
    seeded_portfolio_session: Any, golden_returns_df: pd.DataFrame
) -> None:
    """When position-size is the tightest binding constraint and other
    checks have lower ratios, utilization tracks the position-size ratio.

    confidence=40 maps to "low" -> derived size = 2.5%. Cap = 10%. Ratio
    = 0.25. Sector is Consumer Staples (~14% of portfolio), with 30% cap
    -> post-trade 16.5% / 30% = 0.55. So utilization is dominated by the
    sector check at ~0.55 -- demonstrating max-aggregation, not just
    position-size echo.
    """
    safe = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=99.0,
    )
    deps = RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=safe,
    )
    state = _state(
        ticker="PG",
        thesis=_thesis(ticker="PG", confidence=40),
        candidate_metadata={"sector": "Consumer Staples"},
    )
    with risk_manager_agent.override(
        model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
    ):
        result = _run_node(state, deps)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "APPROVED"
    # Strictly between 0 and 1 -- regression guard against the all-zero
    # bug AND against the "always 1.0" anti-pattern.
    assert 0.0 < assessment["utilization"] < 1.0
