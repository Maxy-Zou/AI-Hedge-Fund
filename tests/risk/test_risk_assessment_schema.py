"""Tests for the RiskAssessment and Violation schemas.

Verifies T-06-02 (LLM cannot tamper with status) at the schema layer:
- ``status`` is a Literal so the LLM can only emit "APPROVED" or "VETOED"
  (semantic overwrite is done by the risk_manager_node in plan 06-05)
- ``constraint_violated`` is a Literal union over the 8 enumerated rule names
- ``Violation`` is frozen (immutable) so internal check results cannot be
  mutated between production and consumption
- ``policy_sha`` is mandatory (64-char hex) -- ensures every assessment is
  tied to a specific RiskPolicy version (T-06-04 audit)
"""

from __future__ import annotations

import pytest
from ai_hedge_fund.schemas.risk import RiskAssessment, Violation
from pydantic import ValidationError

# Valid 64-char hex SHA used across tests.
_SHA: str = "0" * 64


def test_risk_assessment_validates_minimal_approved() -> None:
    """Test 1: Minimal APPROVED instance validates."""
    assessment = RiskAssessment(
        ticker="AAPL",
        status="APPROVED",
        rationale="Within all risk limits",
        policy_sha=_SHA,
    )
    assert assessment.ticker == "AAPL"
    assert assessment.status == "APPROVED"
    assert assessment.constraint_violated is None
    assert assessment.observed is None
    assert assessment.limit is None


def test_risk_assessment_validates_vetoed_with_violation_details() -> None:
    """Test 2: VETOED instance with constraint details validates."""
    assessment = RiskAssessment(
        ticker="TSLA",
        status="VETOED",
        constraint_violated="max_single_position_pct",
        observed=15.0,
        limit=10.0,
        rationale="Position size 15% exceeds 10% cap",
        policy_sha=_SHA,
    )
    assert assessment.status == "VETOED"
    assert assessment.constraint_violated == "max_single_position_pct"
    assert assessment.observed == 15.0
    assert assessment.limit == 10.0


def test_risk_assessment_rejects_invalid_status() -> None:
    """Test 3: status='MAYBE' raises ValidationError (Literal union)."""
    with pytest.raises(ValidationError):
        RiskAssessment(
            ticker="AAPL",
            status="MAYBE",  # type: ignore[arg-type]
            rationale="ok",
            policy_sha=_SHA,
        )


def test_risk_assessment_rejects_invalid_constraint_name() -> None:
    """Test 4: Unknown constraint_violated name raises ValidationError."""
    with pytest.raises(ValidationError):
        RiskAssessment(
            ticker="AAPL",
            status="VETOED",
            constraint_violated="made_up_rule",  # type: ignore[arg-type]
            observed=1.0,
            limit=0.5,
            rationale="bad",
            policy_sha=_SHA,
        )


def test_risk_assessment_rejects_empty_rationale() -> None:
    """Test 5: Empty rationale (min_length=1) raises ValidationError."""
    with pytest.raises(ValidationError):
        RiskAssessment(
            ticker="AAPL",
            status="APPROVED",
            rationale="",
            policy_sha=_SHA,
        )


def test_risk_assessment_requires_policy_sha() -> None:
    """Test 6: policy_sha has no default -- omission raises ValidationError."""
    with pytest.raises(ValidationError):
        RiskAssessment(  # type: ignore[call-arg]
            ticker="AAPL",
            status="APPROVED",
            rationale="ok",
        )


def test_violation_is_frozen() -> None:
    """Test 7: Violation carries name/observed/limit and is immutable."""
    violation = Violation(
        name="max_single_position_pct",
        observed=15.0,
        limit=10.0,
    )
    assert violation.name == "max_single_position_pct"
    assert violation.observed == 15.0
    assert violation.limit == 10.0
    # Frozen -- assignment raises ValidationError in Pydantic v2.
    with pytest.raises(ValidationError):
        violation.observed = 20.0  # type: ignore[misc]


def test_risk_assessment_importable_from_schemas_package() -> None:
    """Test 8: RiskAssessment re-exported from ai_hedge_fund.schemas."""
    from ai_hedge_fund.schemas import RiskAssessment as Re_RiskAssessment
    from ai_hedge_fund.schemas import Violation as Re_Violation

    assert Re_RiskAssessment is RiskAssessment
    assert Re_Violation is Violation
