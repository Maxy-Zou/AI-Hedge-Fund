"""Warm-up tracker for per-market snapshot baseline collection.

Tracks how many snapshots have been collected per market ticker.
Phase 3 signal detectors call is_warmed_up(ticker) before computing anomaly scores —
markets that have not yet crossed the warmup threshold are silently skipped (DATA-06).

Warm-up state is intentionally in-process (not persisted to DB). A restarted daemon
must re-collect baseline data from scratch to ensure statistical validity.
"""

from __future__ import annotations

import threading


class WarmupTracker:
    """Tracks per-market snapshot count to enforce baseline collection period.

    Thread-safe via a Lock — safe to call from APScheduler job threads even
    though max_instances=1 makes overlap unlikely in practice.

    Args:
        threshold: Number of snapshots a market must accumulate before
                   it is considered warmed up and eligible for signal detection.
    """

    def __init__(self, threshold: int) -> None:
        if threshold <= 0:
            msg = "threshold must be > 0"
            raise ValueError(msg)
        self._threshold = threshold
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def record(self, ticker: str) -> None:
        """Increment snapshot count for ticker by one.

        Args:
            ticker: Kalshi market ticker (e.g., "PRES-24-DJT-YES").
        """
        with self._lock:
            self._counts[ticker] = self._counts.get(ticker, 0) + 1

    def is_warmed_up(self, ticker: str) -> bool:
        """Return True if ticker has collected >= threshold snapshots.

        Args:
            ticker: Kalshi market ticker to check.

        Returns:
            True if warmed up and eligible for signal detection.
        """
        with self._lock:
            return self._counts.get(ticker, 0) >= self._threshold

    def status(self) -> dict[str, int]:
        """Return a copy of current snapshot counts for all tracked tickers.

        Returns a new dict — callers may mutate it freely without affecting
        internal state (immutability convention per fund CLAUDE.md).

        Returns:
            Dict mapping ticker -> snapshot count.
        """
        with self._lock:
            return dict(self._counts)
