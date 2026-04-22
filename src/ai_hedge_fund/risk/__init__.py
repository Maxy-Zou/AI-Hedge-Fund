"""Risk management subpackage.

Exposes the Pydantic ``RiskPolicy`` schema, the YAML loader, and the
SHA-256 policy fingerprint helper. Downstream plans (06-02 through 06-06)
consume these primitives via ``from ai_hedge_fund.risk import ...``.

Threat mitigations (see ``06-01-PLAN.md::threat_model``):
    T-06-01: Tampering / unknown-key drift -- ``load_policy`` uses
             ``yaml.safe_load`` exclusively; ``RiskPolicy`` uses
             ``ConfigDict(extra="forbid")``.
    T-06-04: Policy drift without audit -- ``compute_policy_sha`` produces a
             deterministic SHA-256 over canonical-JSON dump.
"""

from __future__ import annotations

from ai_hedge_fund.risk.checks import (
    check_exclusions,
    check_position_size,
    check_sector_concentration,
)
from ai_hedge_fund.risk.policy import RiskPolicy, compute_policy_sha, load_policy
from ai_hedge_fund.risk.portfolio import (
    PortfolioSnapshot,
    PortfolioSnapshotPosition,
    load_portfolio,
    seed_portfolio_from_csv,
)
from ai_hedge_fund.risk.sizing import derive_candidate_size_pct

__all__ = [
    "PortfolioSnapshot",
    "PortfolioSnapshotPosition",
    "RiskPolicy",
    "check_exclusions",
    "check_position_size",
    "check_sector_concentration",
    "compute_policy_sha",
    "derive_candidate_size_pct",
    "load_policy",
    "load_portfolio",
    "seed_portfolio_from_csv",
]
