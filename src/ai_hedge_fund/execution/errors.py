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
    """The broker host is not a paper endpoint (does not contain 'paper-api')."""


class NoPriceAvailable(ExecutionError):
    """No cached adj-close on or before the as-of date for the ticker."""


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


class TransientBrokerError(ExecutionError):
    """A retryable broker/transport failure (5xx, timeout)."""
