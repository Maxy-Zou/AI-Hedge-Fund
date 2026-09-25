"""Apportion broker cash across the signals that held the ticker (Phase 11, 11-SPEC s5).

The broker pays the *account*; attribution needs it per *signal*. Each holder
gets ``amount * weight / total`` floored, and the leftover cents go one each to
the lowest signal ids, so the credits always sum to exactly what the broker
paid (11-PREMORTEM #15). Pure; integer arithmetic only.
"""

from __future__ import annotations

from collections.abc import Mapping


def apportion(amount_cents: int, weights: Mapping[int, int]) -> dict[int, int]:
    """Split ``amount_cents`` across signal ids in proportion to ``weights`` (shares held).

    Holders with zero weight get nothing. With no holders at all the result is
    empty -- the caller decides what an unallocated dividend means.

    Raises:
        ValueError: a weight is negative.
    """
    if any(w < 0 for w in weights.values()):
        raise ValueError(f"negative weight in {dict(weights)}")
    holders = {sid: w for sid, w in sorted(weights.items()) if w > 0}
    total = sum(holders.values())
    if total == 0:
        return {}
    shares = {sid: amount_cents * w // total for sid, w in holders.items()}
    leftover = amount_cents - sum(shares.values())  # 0 <= leftover < len(holders)
    return {
        sid: cents + (1 if i < leftover else 0) for i, (sid, cents) in enumerate(shares.items())
    }
