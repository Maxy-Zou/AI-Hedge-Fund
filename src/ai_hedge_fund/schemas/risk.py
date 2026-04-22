"""Risk management output schemas.

``RiskAssessment`` is the authoritative decision record produced by the
Phase 6 ``risk_manager_node``: for each (ticker, signal) pair the pipeline
records the ``APPROVED`` / ``VETOED`` outcome, the first-violated constraint
(if any), the observed and limit values that triggered the check, an LLM-
authored rationale, and the SHA-256 of the ``RiskPolicy`` that produced the
decision.

``Violation`` is the internal deterministic check result returned by
``ai_hedge_fund.risk.checks`` (plan 06-03). It is consumed by the risk-
manager node, which maps it onto the ``constraint_violated`` / ``observed``
/ ``limit`` fields of ``RiskAssessment``. It is NOT an LLM output schema.

Threat mitigations (see ``06-01-PLAN.md::threat_model``):
    T-06-02: Veto bypass via LLM-authored status -- ``status`` is a
             Literal["APPROVED", "VETOED"], so the LLM cannot emit any other
             value. The semantic overwrite (LLM value discarded, deterministic
             check result wins) is enforced by plan 06-05's risk_manager_node.
    T-06-04: Policy drift without audit -- ``policy_sha`` is a mandatory
             64-char hex field; every assessment is tied to a specific
             ``RiskPolicy`` version.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONSTRAINT_NAMES = Literal[
    "max_single_position_pct",
    "max_sector_pct",
    "max_total_exposure_pct",
    "max_correlation_with_portfolio",
    "max_projected_drawdown_pct",
    "excluded_instrument_type",
    "excluded_sector",
    "insufficient_price_history",
]
"""Union of every policy constraint name that can trigger a veto.

Kept in sync with ``RiskPolicy`` field names (plus two derived names --
``excluded_instrument_type``, ``excluded_sector``, ``insufficient_price_history``
-- that describe check outcomes rather than raw policy fields).
"""


class Violation(BaseModel):
    """Internal deterministic check result.

    Produced by ``ai_hedge_fund.risk.checks`` (plan 06-03); consumed by
    ``risk_manager_node`` (plan 06-05) which maps it onto the
    ``constraint_violated`` / ``observed`` / ``limit`` fields of
    ``RiskAssessment``.

    NOT an LLM output schema -- the LLM sees the rationale text, not this
    structure. Frozen so a ``Violation`` produced by one check cannot be
    mutated between production and consumption.
    """

    model_config = ConfigDict(frozen=True)

    name: CONSTRAINT_NAMES = Field(
        description="The policy constraint that was violated",
    )
    observed: float = Field(
        description="Observed value that triggered the violation (same unit as the limit)",
    )
    limit: float = Field(
        description="Policy threshold that was exceeded (same unit as observed)",
    )


class RiskAssessment(BaseModel):
    """Authoritative decision record for a (ticker, signal) pair.

    Produced by the Phase 6 risk_manager_node. ``status`` is the deterministic
    outcome of the check chain -- any LLM-authored ``status`` value is
    discarded upstream (T-06-02). The ``rationale`` is advisory LLM-authored
    explanation; it cannot affect the decision.
    """

    ticker: str = Field(
        min_length=1,
        max_length=10,
        description="Stock ticker symbol evaluated",
    )
    status: Literal["APPROVED", "VETOED"] = Field(
        description=(
            "Deterministic outcome of the risk check chain. "
            "LLM-authored value is DISCARDED and overwritten by risk_manager_node "
            "(Pitfall 1 + T-06-02)."
        ),
    )
    constraint_violated: CONSTRAINT_NAMES | None = Field(
        default=None,
        description="Name of the first-violated constraint; None if APPROVED.",
    )
    observed: float | None = Field(
        default=None,
        description="Observed value that triggered the violation; None if APPROVED.",
    )
    limit: float | None = Field(
        default=None,
        description="Policy threshold that was exceeded; None if APPROVED.",
    )
    rationale: str = Field(
        min_length=1,
        description=(
            "Advisory LLM-authored explanation of the decision. "
            "CANNOT affect status -- status is deterministic."
        ),
    )
    policy_sha: str = Field(
        min_length=64,
        max_length=64,
        description=(
            "SHA-256 hex of the RiskPolicy used for this assessment. Mandatory for audit (T-06-04)."
        ),
    )
