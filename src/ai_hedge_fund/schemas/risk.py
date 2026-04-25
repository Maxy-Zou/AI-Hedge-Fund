"""Risk management output schemas.

``RiskAssessment`` is the authoritative decision record produced by the
Phase 6 ``risk_manager_node``: for each (ticker, signal) pair the pipeline
records the ``APPROVED`` / ``VETOED`` outcome, the first-violated constraint
(if any), the observed and limit values that triggered the check, the
deterministic policy-utilization ratio, an LLM-authored rationale, and the
SHA-256 of the ``RiskPolicy`` that produced the decision.

``Violation`` is the internal deterministic check result returned by
``ai_hedge_fund.risk.checks`` (plan 06-03). It is consumed by the risk-
manager node, which maps it onto the ``constraint_violated`` / ``observed``
/ ``limit`` fields of ``RiskAssessment``. It is NOT an LLM output schema.

``CheckResult`` is the new (utilization, Violation | None) tuple returned
by every check helper so the node can aggregate utilization across all
checks (08-RESEARCH.md A9): ``utilization = min(1.0, max(ratios))``,
exposed via ``RiskAssessment.utilization``. The ratio is the per-check
share of the policy budget consumed by the candidate, in [0, +inf) before
clamping. Values >=1.0 indicate the check fired (or would have fired).

Threat mitigations (see ``06-01-PLAN.md::threat_model``):
    T-06-02: Veto bypass via LLM-authored status -- ``status`` is a
             Literal["APPROVED", "VETOED"], so the LLM cannot emit any other
             value. The semantic overwrite (LLM value discarded, deterministic
             check result wins) is enforced by plan 06-05's risk_manager_node.
    T-06-04: Policy drift without audit -- ``policy_sha`` is a mandatory
             64-char hex field; every assessment is tied to a specific
             ``RiskPolicy`` version.
    T-08-12: LLM-authored risk_score -- ``utilization`` is a Python-derived
             float. ``derive_risk_score`` reads it directly; the LLM never
             authors it.
"""

from __future__ import annotations

from typing import Literal, NamedTuple

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


class CheckResult(NamedTuple):
    """Tuple returned by every deterministic risk check helper.

    Carries the per-check utilization ratio (observed / limit, unclamped)
    AND the optional :class:`Violation` produced when the check fires.
    The node aggregates ``ratio`` across all checks for the assessment's
    ``utilization`` field while still using ``violation`` to drive the
    "first violation wins" short-circuit that decides APPROVED / VETOED.

    Frozen by virtue of being a NamedTuple -- callers cannot tamper with
    the result between production (the check) and consumption (the node).
    """

    ratio: float
    violation: Violation | None


class RiskAssessment(BaseModel):
    """Authoritative decision record for a (ticker, signal) pair.

    Produced by the Phase 6 risk_manager_node. ``status`` is the deterministic
    outcome of the check chain -- any LLM-authored ``status`` value is
    discarded upstream (T-06-02). The ``rationale`` is advisory LLM-authored
    explanation; it cannot affect the decision.

    ``utilization`` is the deterministic max-ratio across all checks
    (clamped to [0, 1]). Used by the Phase-8 signal output to derive the
    final ``risk_score``; the LLM never authors it (T-08-12).
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
    utilization: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Max policy-utilization ratio across all deterministic checks, "
            "clamped to [0, 1]. Computed by the node from per-check ratios "
            "(observed/limit) regardless of APPROVED / VETOED status. "
            "Drives the Phase-8 risk_score; never LLM-authored (T-08-12)."
        ),
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
