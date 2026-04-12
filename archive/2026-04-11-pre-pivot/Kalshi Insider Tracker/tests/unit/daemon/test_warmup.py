"""Tests for WarmupTracker (DATA-06: baseline collection before signals fire)."""
from __future__ import annotations

import pytest

from kalshi_tracker.daemon.warmup import WarmupTracker


def test_not_warmed_up() -> None:
    tracker = WarmupTracker(threshold=3)
    assert tracker.is_warmed_up("TICKER-1") is False


def test_warmed_up_at_threshold() -> None:
    tracker = WarmupTracker(threshold=3)
    tracker.record("TICKER-1")
    tracker.record("TICKER-1")
    tracker.record("TICKER-1")
    assert tracker.is_warmed_up("TICKER-1") is True


def test_below_threshold() -> None:
    tracker = WarmupTracker(threshold=3)
    tracker.record("TICKER-1")
    tracker.record("TICKER-1")
    assert tracker.is_warmed_up("TICKER-1") is False


def test_independent_tickers() -> None:
    tracker = WarmupTracker(threshold=2)
    tracker.record("A")
    tracker.record("A")
    assert tracker.is_warmed_up("A") is True
    assert tracker.is_warmed_up("B") is False


def test_status_returns_copy() -> None:
    tracker = WarmupTracker(threshold=5)
    tracker.record("X")
    snapshot = tracker.status()
    snapshot["X"] = 999  # mutate the returned dict
    # internal state should be unchanged
    assert tracker.status()["X"] == 1
