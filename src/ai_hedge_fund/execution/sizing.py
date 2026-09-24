"""Deterministic order sizing (Phase 10, D5).

Pure functions of ``(conviction, price, policy)`` -- no I/O, no LLM. Conviction
below ``min_conviction`` sizes to zero (the caller refuses as below_min_size);
between ``min_conviction`` and ``full_conviction`` the budget scales linearly to
the full ``max_position_pct`` cap. Share count is floored to a whole number so
the notional never exceeds the budget (09-PREMORTEM #9/#10).

The budget is computed in exact rational arithmetic (review R4): float math made
``10_000_000 * 0.01 * 29/50`` come out as 57999.999..., silently dropping a
share exactly at the boundary. ``max_position_pct`` is read as the decimal the
policy file states (``Fraction(str(0.01)) == 1/100``), not its binary float.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ai_hedge_fund.execution.policy import ExecutionPolicy


@dataclass(frozen=True)
class SizeResult:
    shares: int
    notional_cents: int
    scale: float
    price_cents: int


def _exact_scale(conviction: int, policy: ExecutionPolicy) -> Fraction:
    if conviction < policy.min_conviction:
        return Fraction(0)
    if conviction >= policy.full_conviction:
        return Fraction(1)
    span = policy.full_conviction - policy.min_conviction
    return Fraction(conviction - policy.min_conviction, span)


def conviction_scale(conviction: int, policy: ExecutionPolicy) -> float:
    """0.0 below ``min_conviction``; linear to 1.0 at ``full_conviction``; clamped.

    For reporting only -- sizing uses the exact rational, never this float.
    """
    return float(_exact_scale(conviction, policy))


def size_order(conviction: int, price_cents: int, policy: ExecutionPolicy) -> SizeResult:
    """Whole-share size for a signal. Zero shares when scale is 0 or the share is too dear."""
    scale = _exact_scale(conviction, policy)
    budget = policy.nav_cents * Fraction(str(policy.max_position_pct)) * scale
    shares = int(budget // price_cents) if price_cents > 0 else 0
    return SizeResult(
        shares=shares,
        notional_cents=shares * price_cents,
        scale=float(scale),
        price_cents=price_cents,
    )
