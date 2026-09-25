"""Typed errors for Phase 11 mark-to-market (11-SPEC s8).

All inherit :class:`MtmError`. Like the paper store, anything raised after the
session was touched leaves it rolled back and usable.
"""

from __future__ import annotations


class MtmError(Exception):
    """Base class for mark-to-market errors."""


class IncompleteTradingDay(MtmError):
    """``pnl_date`` has not closed yet (or is not a weekday); nothing is written (D6)."""


class FutureInputError(MtmError):
    """A fill or cash event dated after ``pnl_date`` reached the P&L core (temporal guard)."""


class OversoldError(MtmError):
    """Sells exceed the open quantity -- impossible in the long-only book; data is corrupt."""


class ConcurrentRun(MtmError):
    """Another run inserted a (signal, date) row mid-batch; the whole batch was rolled back."""


class AttributionInvariantError(MtmError):
    """An attribution dimension does not sum exactly to the total (criterion 11.3)."""
