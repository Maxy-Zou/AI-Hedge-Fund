"""Type contracts for the execution layer (Phase 4).

ApprovalResult: Returned by RiskGuard.approve() indicating approval decision.
ExecutionResult: Summary of a completed execution cycle (used for testing/logging).

These frozen dataclasses define the interface contract for Plan 02 implementers.
No production logic lives here — this file is for IDE/type-checking support only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalResult:
    """Outcome of a RiskGuard.approve() call.

    Attributes:
        approved: True if the signal may proceed to execution.
        reason: 'approved' | 'per_trade_cap' | 'total_exposure_cap' | 'in_flight' | 'duplicate'
        trade_cost_cents: Computed trade cost in cents. 0 when not approved.
    """

    approved: bool
    reason: str
    trade_cost_cents: int = 0


@dataclass(frozen=True)
class ExecutionResult:
    """Summary of one TradeExecutor.execute() call.

    Attributes:
        trade: The Trade ORM row written (None if below confidence threshold).
        mode: 'paper' | 'live' | 'blocked' | 'skipped'
    """

    trade: object  # Trade | None — avoid circular import with ORM
    mode: str
