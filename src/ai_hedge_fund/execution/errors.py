"""Typed errors for the paper execution surface (Phase 10).

All inherit :class:`ExecutionError`. ``AppendOnlyViolation`` (db layer) is
deliberately not in this family -- it is a programming error, not an
execution outcome.
"""

from __future__ import annotations


class ExecutionError(Exception):
    """Base class for paper-execution errors."""


class MissingBrokerCredentials(ExecutionError):
    """A required ALPACA_PAPER_* value is empty; message names the variable."""


class LiveEndpointRefused(ExecutionError):
    """The broker host is not exactly Alpaca's paper endpoint (https, allow-listed hostname)."""


class BrokerAuthError(ExecutionError):
    """The broker rejected the credentials (401/403).

    Deliberately *not* a :class:`BrokerRejected`: the broker never evaluated the
    order, so nothing is recorded and no attempt is consumed.
    """


class NoPriceAvailable(ExecutionError):
    """No cached adj-close on or before the as-of date for the ticker."""


class InvalidSignal(ExecutionError):
    """The stored analysis/review data is malformed or inconsistent.

    Raised, not recorded: a refusal row is terminal, and malformed data should
    be fixable by a corrected review row (latest review wins).
    """


class SignalNotReviewed(ExecutionError):
    """The analysis row has no linked review row to source a decision from."""


class AlreadySubmitted(ExecutionError):
    """The latest attempt for this signal is already 'submitted'."""


class AlreadyDecided(ExecutionError):
    """The latest attempt for this signal is a terminal refusal."""


class AttemptsExhausted(ExecutionError):
    """The signal has reached the policy's max_attempts."""


class BrokerRejected(ExecutionError):
    """The broker rejected the order; recorded as a 'rejected' row."""


class DuplicateClientOrderId(BrokerRejected):
    """The broker has already seen this client_order_id (idempotency hit)."""


class ClientOrderIdConflict(ExecutionError):
    """The broker holds our client_order_id for an order we would not have placed.

    Raised instead of adopting it -- recording a foreign order as ours would
    corrupt the audit trail.
    """


class TransientBrokerError(ExecutionError):
    """A retryable broker/transport failure (5xx, 429, timeout, connection).

    The order may or may not have reached the broker; a re-run resends the same
    client_order_id, so it is safe either way.
    """
