"""Credit broker dividend cash to the signals that held the ticker (Phase 11, 11-SPEC s5).

The broker pays the *account* for ``paid_shares`` shares (the activity's ``qty``).
A signal holding ``shares`` of them is credited ``amount * shares / paid_shares``,
truncated toward zero. The credit depends only on that signal's own holding, so
shares held outside any signal, a fill ingested after the day was marked, or an
oversold holder can never move cash onto another signal (review H5), and the
credits never exceed what was paid. Pure; exact integer/Decimal arithmetic.
"""

from __future__ import annotations

from decimal import Decimal, DecimalException
from typing import Any


def paid_shares(payload: dict[str, Any]) -> Decimal | None:
    """The share count the broker paid on, from a cash event's raw payload; None if unusable."""
    value = payload.get("qty")
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    try:
        qty = Decimal(str(value))
    except DecimalException:
        return None
    return qty if qty.is_finite() and qty > 0 else None


def signal_credit(amount_cents: int, shares: int, paid: Decimal) -> int:
    """``amount_cents * shares / paid``, truncated toward zero (never more than paid).

    Raises:
        ValueError: ``shares`` is negative or ``paid`` is not positive.
    """
    if shares < 0 or paid <= 0:
        raise ValueError(f"invalid holding {shares} of {paid} paid shares")
    return int(Decimal(amount_cents) * shares / paid)  # int() truncates toward zero
