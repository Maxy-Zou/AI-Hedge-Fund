"""RED tests for SignalEngine (SIG-05, SIG-06).

These tests FAIL on import — kalshi_tracker.signals.engine does not exist yet.
That is the correct RED state: tests define the interface before implementation.

Test coverage:
  - Warmup gate: unwarmed markets are skipped entirely
  - Resolution suppression: close_time within blackout period blocks signals
  - No suppression when close_time is None or outside blackout window
  - Signal persistence: warmed+unsuppressed market triggers DB write
  - Cooldown deduplication: recent signal for same (ticker, signal_type) skipped
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

# RED: these imports will raise ModuleNotFoundError until Plan 03 is executed.
from kalshi_tracker.signals.engine import SignalEngine

from kalshi_tracker.config import SignalSettings
from kalshi_tracker.daemon.warmup import WarmupTracker
from kalshi_tracker.db.models import Signal

from .conftest import snapshot_factory

_TICKER = "TEST-1"


def _make_session_factory(session: MagicMock) -> MagicMock:
    """Return a session_factory mock whose context manager yields session."""
    factory = MagicMock()
    factory.return_value.__enter__ = MagicMock(return_value=session)
    factory.return_value.__exit__ = MagicMock(return_value=False)
    return factory


def _make_warmed_tracker(ticker: str = _TICKER) -> WarmupTracker:
    """Return a WarmupTracker that reports ticker as warmed up."""
    tracker = WarmupTracker(threshold=1)
    tracker.record(ticker)
    return tracker


def _make_settings(**overrides: object) -> SignalSettings:
    """Return a SignalSettings with test-friendly defaults plus any overrides."""
    defaults = {
        "volume_z_threshold": 2.5,
        "volume_window": 60,
        "price_move_threshold": 0.15,
        "price_window": 60,
        "resolution_blackout_minutes": 30,
        "min_confidence": 0.0,
        "signal_cooldown_seconds": 300,
    }
    defaults.update(overrides)
    return SignalSettings(**defaults)


def _make_firing_detector(signal_type: str = "volume_spike", confidence: float = 0.8) -> MagicMock:
    """Return a mock detector whose detect() always returns a DetectionResult."""
    from kalshi_tracker.signals.types import DetectionResult

    detector = MagicMock()
    detector.detect.return_value = DetectionResult(
        signal_type=signal_type,
        confidence=confidence,
        details={"z_score": 5.0},
    )
    return detector


# ---------------------------------------------------------------------------
# Warmup gate
# ---------------------------------------------------------------------------

def test_engine_skips_unwarmed_market(mock_session: MagicMock) -> None:
    """Engine returns [] and writes nothing when market is not warmed up."""
    cold = WarmupTracker(threshold=100)
    session_factory = _make_session_factory(mock_session)
    settings = _make_settings()

    engine = SignalEngine(
        session_factory=session_factory,
        warmup=cold,
        settings=settings,
    )

    result = engine.run(_TICKER)

    assert result == []
    mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Resolution suppression
# ---------------------------------------------------------------------------

@freeze_time("2025-01-01 12:00:00+00:00")
def test_resolution_suppression(mock_session: MagicMock) -> None:
    """Engine returns [] when close_time is within the blackout window."""
    warmup = _make_warmed_tracker()
    session_factory = _make_session_factory(mock_session)
    # Blackout = 30 min; close_time = 20 min from now → inside blackout
    close_time = datetime(2025, 1, 1, 12, 20, 0, tzinfo=UTC)
    settings = _make_settings(resolution_blackout_minutes=30)

    engine = SignalEngine(
        session_factory=session_factory,
        warmup=warmup,
        settings=settings,
    )

    result = engine.run(_TICKER, close_time=close_time)

    assert result == []
    mock_session.add.assert_not_called()


@freeze_time("2025-01-01 12:00:00+00:00")
def test_no_suppression_without_close_time(mock_session: MagicMock) -> None:
    """Engine does NOT suppress when close_time is None.

    With no close_time, suppression is skipped — the engine may produce signals.
    We verify suppression doesn't block (add may or may not be called depending
    on whether mock detectors fire, but we confirm run() doesn't return early).
    """
    warmup = _make_warmed_tracker()
    session_factory = _make_session_factory(mock_session)
    settings = _make_settings(resolution_blackout_minutes=30)
    firing_detector = _make_firing_detector()

    engine = SignalEngine(
        session_factory=session_factory,
        warmup=warmup,
        settings=settings,
        detectors=[firing_detector],
    )

    result = engine.run(_TICKER, close_time=None)

    # Suppression did not block — run() returned something (list, may be non-empty)
    assert isinstance(result, list)
    # Detector was invoked (suppression didn't short-circuit before detection)
    firing_detector.detect.assert_called()


@freeze_time("2025-01-01 12:00:00+00:00")
def test_no_suppression_outside_blackout(mock_session: MagicMock) -> None:
    """Engine does NOT suppress when close_time is outside the blackout window."""
    warmup = _make_warmed_tracker()
    session_factory = _make_session_factory(mock_session)
    # Blackout = 30 min; close_time = 60 min from now → outside blackout
    close_time = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)
    settings = _make_settings(resolution_blackout_minutes=30)
    firing_detector = _make_firing_detector()

    engine = SignalEngine(
        session_factory=session_factory,
        warmup=warmup,
        settings=settings,
        detectors=[firing_detector],
    )

    result = engine.run(_TICKER, close_time=close_time)

    assert isinstance(result, list)
    firing_detector.detect.assert_called()


# ---------------------------------------------------------------------------
# Signal persistence
# ---------------------------------------------------------------------------

@freeze_time("2025-01-01 12:00:00+00:00")
def test_engine_persists_signal(mock_session: MagicMock) -> None:
    """Engine adds a Signal row when warmed up, not suppressed, and detector fires."""
    warmup = _make_warmed_tracker()
    session_factory = _make_session_factory(mock_session)
    settings = _make_settings()
    firing_detector = _make_firing_detector(signal_type="volume_spike", confidence=0.9)

    engine = SignalEngine(
        session_factory=session_factory,
        warmup=warmup,
        settings=settings,
        detectors=[firing_detector],
    )

    result = engine.run(_TICKER)

    assert len(result) >= 1
    mock_session.add.assert_called()
    # Verify the added object has the correct ticker
    added_obj = mock_session.add.call_args[0][0]
    assert added_obj.ticker == _TICKER


# ---------------------------------------------------------------------------
# Cooldown deduplication
# ---------------------------------------------------------------------------

@freeze_time("2025-01-01 12:00:00+00:00")
def test_engine_cooldown_skips_duplicate(mock_session: MagicMock) -> None:
    """Engine returns [] when a recent signal for (ticker, signal_type) exists in DB.

    Simulates a Signal row captured_at = now - 60s (within default cooldown 300s).
    Engine should detect the duplicate and skip persistence.
    """
    warmup = _make_warmed_tracker()
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Set up recent Signal in mock DB query chain
    recent_signal = MagicMock(spec=Signal)
    recent_signal.detected_at = now - timedelta(seconds=60)
    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        recent_signal
    ]

    session_factory = _make_session_factory(mock_session)
    settings = _make_settings(signal_cooldown_seconds=300)
    firing_detector = _make_firing_detector(signal_type="volume_spike")

    engine = SignalEngine(
        session_factory=session_factory,
        warmup=warmup,
        settings=settings,
        detectors=[firing_detector],
    )

    result = engine.run(_TICKER)

    assert result == []
    mock_session.add.assert_not_called()
