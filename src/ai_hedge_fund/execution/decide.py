"""Pure execution decision: signal -> order plan or typed refusal (Phase 10, D5/D7).

No I/O, no LLM. The check order *is* the audit order (09-PREMORTEM #5/#6): risk
veto first (EXEC-04 circuit breaker), then reviewer rejection, then direction,
then the long-only policy, then price availability, then minimum size. A veto or
rejection is decided without a price or a final signal so a blocked signal never
reaches sizing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ai_hedge_fund.execution.policy import ExecutionPolicy
from ai_hedge_fund.execution.sizing import SizeResult, size_order

RefusalStatus = Literal["refused_veto", "refused_review", "refused_policy"]
RefusalReason = Literal[
    "risk_vetoed", "review_rejected", "neutral_direction", "long_only", "no_price", "below_min_size"
]


class Refusal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: RefusalStatus
    reason: RefusalReason


class OrderPlan(BaseModel):
    # arbitrary_types_allowed: SizeResult is a frozen dataclass, not a BaseModel.
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: int
    limit_price_cents: int | None
    size: SizeResult


Decision = Refusal | OrderPlan


def decide(
    final_signal: dict[str, Any] | None,
    *,
    risk_status: str,
    review_status: str | None,
    price_cents: int | None,
    policy: ExecutionPolicy,
) -> Decision:
    """Return an OrderPlan to submit, or a typed Refusal to record."""
    # 1. Risk veto -- EXEC-04, decided before price or signal is even needed.
    if risk_status == "VETOED":
        return Refusal(status="refused_veto", reason="risk_vetoed")

    # 2. Human reviewer rejected.
    if review_status == "REJECTED":
        return Refusal(status="refused_review", reason="review_rejected")

    # Below here a final_signal is required; its absence is a policy refusal.
    if final_signal is None:
        return Refusal(status="refused_policy", reason="neutral_direction")

    direction = final_signal.get("direction")

    # 3. Direction.
    if direction == "neutral":
        return Refusal(status="refused_policy", reason="neutral_direction")

    # 4. Long-only policy (D7).
    if direction == "short" and policy.long_only:
        return Refusal(status="refused_policy", reason="long_only")

    # 5. Price availability.
    if price_cents is None:
        return Refusal(status="refused_policy", reason="no_price")

    # 6. Minimum size.
    conviction = int(final_signal.get("conviction") or 0)
    size = size_order(conviction=conviction, price_cents=price_cents, policy=policy)
    if size.shares <= 0:
        return Refusal(status="refused_policy", reason="below_min_size")

    side: Literal["buy", "sell"] = "buy" if direction == "long" else "sell"
    limit_price_cents = (
        _limit_price(side, price_cents, policy) if policy.order_type == "limit" else None
    )
    return OrderPlan(
        side=side,
        order_type=policy.order_type,
        quantity=size.shares,
        limit_price_cents=limit_price_cents,
        size=size,
    )


def _limit_price(side: str, price_cents: int, policy: ExecutionPolicy) -> int:
    """Marketable limit: pay up (buy) / accept down (sell) by the policy offset."""
    offset = price_cents * policy.limit_offset_bps // 10_000
    return price_cents + offset if side == "buy" else max(1, price_cents - offset)
