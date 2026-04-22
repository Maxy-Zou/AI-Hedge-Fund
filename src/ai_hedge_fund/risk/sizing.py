"""Candidate-position sizing: map conviction to candidate weight (A4).

This module encodes Assumption A4 from ``06-RESEARCH.md``: a fixed-step
mapping from ``SignalOutput.conviction`` to a candidate position size
(expressed as a percent of portfolio value). High conviction allocates a
full ``max_single_position_pct`` slot; medium / low conviction scale the
slot down by the policy multipliers.

The function is pure (no I/O, no DB, no LLM). The returned float is in the
same unit as :attr:`RiskPolicy.max_single_position_pct` -- raw percent
(e.g., ``10.0`` means 10% of portfolio value).

Rationale: keeping the mapping in one place means policy edits (tighten the
multipliers, or bump ``max_single_position_pct``) propagate without touching
downstream checks. The mapping is deliberately data-driven rather than
hard-coded; swapping in a Kelly-criterion or ERC-weighted mapping later is a
three-line policy edit, not a code change.
"""

from __future__ import annotations

from typing import Literal

from ai_hedge_fund.risk.policy import RiskPolicy

Conviction = Literal["low", "medium", "high"]


def derive_candidate_size_pct(conviction: Conviction, policy: RiskPolicy) -> float:
    """Return the candidate position size percent for a conviction level.

    Args:
        conviction: One of ``"low"``, ``"medium"``, ``"high"`` from
            :class:`ai_hedge_fund.schemas.agents.SignalOutput`.
        policy: Validated :class:`RiskPolicy` supplying the
            ``max_single_position_pct`` slot and the three size multipliers.

    Returns:
        Raw percent of portfolio value to allocate, e.g. ``10.0`` for 10%.

    Raises:
        ValueError: If ``conviction`` is not one of the three expected
            literals. Raising (rather than defaulting) forces callers to
            surface malformed upstream state instead of silently shrinking
            positions.
    """
    if conviction == "high":
        return policy.max_single_position_pct * policy.size_high_conviction_multiplier
    if conviction == "medium":
        return policy.max_single_position_pct * policy.size_medium_conviction_multiplier
    if conviction == "low":
        return policy.max_single_position_pct * policy.size_low_conviction_multiplier
    raise ValueError(f"Unknown conviction {conviction!r}; expected one of 'low', 'medium', 'high'")
