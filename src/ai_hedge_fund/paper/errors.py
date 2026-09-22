"""Typed errors raised by the paper-trading store and seeders.

All inherit :class:`PaperStoreError` so Phase 10's submit loop can catch
the family. :class:`ai_hedge_fund.db.append_only.AppendOnlyViolation` is
deliberately *not* in this family -- it signals a programming error, not a
data condition.

Contract: whenever the store raises one of these after touching the
session, it has already rolled the session back; the caller may continue.
"""

from __future__ import annotations


class PaperStoreError(Exception):
    """Base class for paper-trading data-layer errors."""


class SignalNotFound(PaperStoreError):
    """No ``episodic_memory`` row with the given id."""


class SignalWrongRecordType(PaperStoreError):
    """The episodic row exists but is not ``record_type='analysis'``."""


class SignalTickerMismatch(PaperStoreError):
    """The denormalized ticker does not match the episodic row's ticker."""


class SeedFormatError(PaperStoreError):
    """A seed CSV does not have the expected header."""


class AmbiguousSignal(PaperStoreError):
    """Seeder: more than one analysis row matches ``(ticker, as_of_date)``."""


class DuplicateSubmission(PaperStoreError):
    """``(signal_id, attempt_no)`` or ``broker_order_id`` already recorded."""


class TradeNotFound(PaperStoreError):
    """No ``paper_trades`` row with the given id (or broker_order_id, for seeders)."""


class DuplicateFill(PaperStoreError):
    """``broker_fill_id`` already recorded."""
