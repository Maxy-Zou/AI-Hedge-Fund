"""Deterministic risk checks: position size, sector concentration, exclusions.

Pure-Python helpers called in order by ``risk_manager_node`` (plan 06-05).
Each check returns :class:`Violation` when the policy is breached and
``None`` when the candidate is acceptable on that dimension. The caller
short-circuits on the first violation -- "first violation wins" is the
contract documented in ``06-RESEARCH.md`` and encoded in 06-05's must_haves.

Never cap. RISK-02 explicitly requires rejection (not silent capping) when
a candidate exceeds the position-size limit; the returned ``Violation``
carries the observed + limit so the rationale can reference the specific
threshold that was breached.

Pre-trade convention (Pitfall 6): sector concentration is computed as
``current_sector_weight + candidate_size``. Callers pass the pre-trade
snapshot; they never add the candidate into the portfolio themselves.

Threat mitigations:
    T-06-02: Veto bypass by silent capping -- see ``check_position_size``
             docstring; acceptance criterion greps that ``min(...)`` is
             never applied between ``candidate_size_pct`` and
             ``policy.max_single_position_pct``.
    T-06-07: Sector double-counting -- pre-trade convention prevents the
             candidate being counted twice in ``check_sector_concentration``.
"""

from __future__ import annotations

from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import PortfolioSnapshot
from ai_hedge_fund.schemas.risk import Violation


def check_position_size(candidate_size_pct: float, policy: RiskPolicy) -> Violation | None:
    """Reject when the candidate size exceeds ``policy.max_single_position_pct``.

    RISK-02 hard-limit contract: a signal requesting more than the cap is
    REJECTED. Do not silently cap the size (that would violate the success
    criterion "rejection reason references the specific limit"). The
    boundary is inclusive -- a candidate exactly at the cap is approved.

    Pitfall: if you are tempted to write ``min(candidate, limit)`` here, you
    are violating RISK-02. The node emits a veto; the signal generator is
    responsible for resizing in a future revision, not this check.
    """
    if candidate_size_pct > policy.max_single_position_pct:
        return Violation(
            name="max_single_position_pct",
            observed=candidate_size_pct,
            limit=policy.max_single_position_pct,
        )
    return None


def check_sector_concentration(
    candidate_sector: str,
    candidate_size_pct: float,
    portfolio: PortfolioSnapshot,
    policy: RiskPolicy,
) -> Violation | None:
    """Reject when post-trade sector weight exceeds ``policy.max_sector_pct``.

    Pre-trade convention (Pitfall 6): the post-trade weight is simply the
    pre-trade sector weight plus the candidate's proposed size. This keeps
    the math unambiguous and prevents the candidate from being counted
    twice when the sector already contains overlapping positions.
    """
    post_sector_pct = portfolio.sector_weight_pct(candidate_sector) + candidate_size_pct
    if post_sector_pct > policy.max_sector_pct:
        return Violation(
            name="max_sector_pct",
            observed=post_sector_pct,
            limit=policy.max_sector_pct,
        )
    return None


def check_exclusions(
    candidate_sector: str,
    candidate_instrument_type: str,
    policy: RiskPolicy,
) -> Violation | None:
    """Reject when the candidate's instrument type or sector is blacklisted.

    Evaluates instrument type before sector so the returned violation name
    reflects the tightest-scoped exclusion first. Both fields read from the
    policy's configurable lists, so adding a new exclusion is a YAML edit.
    """
    if candidate_instrument_type in policy.excluded_instrument_types:
        return Violation(
            name="excluded_instrument_type",
            observed=1.0,
            limit=0.0,
        )
    if candidate_sector in policy.excluded_sectors:
        return Violation(
            name="excluded_sector",
            observed=1.0,
            limit=0.0,
        )
    return None
