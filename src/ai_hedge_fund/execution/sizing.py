"""Deterministic order sizing (Phase 10, D5).

Pure functions of ``(conviction, price, policy)`` -- no I/O, no LLM. Conviction
below ``min_conviction`` sizes to zero (the caller refuses as below_min_size);
between ``min_conviction`` and ``full_conviction`` the budget scales linearly to
the full ``max_position_pct`` cap. Share count is floored to a whole number so
the notional never exceeds the budget (09-PREMORTEM #9/#10).
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_hedge_fund.execution.policy import ExecutionPolicy


@dataclass(frozen=True)
class SizeResult:
    shares: int
    notional_cents: int
    scale: float
    price_cents: int


def conviction_scale(conviction: int, policy: ExecutionPolicy) -> float:
    """0.0 below ``min_conviction``; linear to 1.0 at ``full_conviction``; clamped."""
    if conviction < policy.min_conviction:
        return 0.0
    if conviction >= policy.full_conviction:
        return 1.0
    span = policy.full_conviction - policy.min_conviction
    return (conviction - policy.min_conviction) / span


def size_order(conviction: int, price_cents: int, policy: ExecutionPolicy) -> SizeResult:
    """Whole-share size for a signal. Zero shares when scale is 0 or the share is too dear."""
    scale = conviction_scale(conviction, policy)
    budget_cents = int(policy.nav_cents * policy.max_position_pct * scale)
    shares = budget_cents // price_cents if price_cents > 0 else 0
    return SizeResult(
        shares=shares,
        notional_cents=shares * price_cents,
        scale=scale,
        price_cents=price_cents,
    )
