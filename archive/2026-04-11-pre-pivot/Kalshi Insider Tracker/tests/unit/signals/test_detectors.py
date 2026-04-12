"""RED tests for VolumeSpikeDetector, PriceMoveDetector (SIG-01, SIG-02),
TimingClusterDetector (SIG-03), and WinStreakDetector stub (SIG-04).

These tests FAIL on import — kalshi_tracker.signals.detectors does not exist yet.
That is the correct RED state: tests define the interface before implementation.

Test coverage:
  - VolumeSpikeDetector: above threshold, below threshold, zero std guard, confidence clamped
  - PriceMoveDetector: above threshold, zero range guard
  - TimingClusterDetector: fires on burst, None on insufficient snapshots, None on dead market,
      None on uniform volume, confidence clamped to 1.0
  - WinStreakDetector: always returns None (SIG-04 infeasibility stub)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

# RED: these imports will raise ModuleNotFoundError until Plan 02 is executed.
from kalshi_tracker.signals.detectors import PriceMoveDetector, VolumeSpikeDetector

# RED: TimingClusterDetector and WinStreakDetector do not exist yet (Plan 06-02 implements them).
from kalshi_tracker.signals.detectors import TimingClusterDetector, WinStreakDetector
from kalshi_tracker.signals.types import DetectionResult

from .conftest import snapshot_factory


def _make_volume_snapshots(
    baseline_count: int = 60,
    baseline_vol: int = 300,
    spike_vol: int = 1500,
) -> list:
    """Build snapshots with a volume spike as the last element.

    First `baseline_count` snapshots have volume_24h=baseline_vol.
    The final snapshot has volume_24h=spike_vol.
    """
    volumes = [baseline_vol] * baseline_count + [spike_vol]
    prices = [50] * (baseline_count + 1)  # price irrelevant for volume test
    return snapshot_factory("VOL-TEST-1", volumes, prices)


def _make_price_snapshots(
    baseline_prices: list[int] | None = None,
    spike_price: int = 99,
) -> list:
    """Build snapshots with a price spike as the last element.

    First len(baseline_prices) snapshots alternate within a tight range.
    The final snapshot has last_price=spike_price (far outside range).
    """
    if baseline_prices is None:
        baseline_prices = [45, 46, 45, 46, 45, 46, 45, 46, 45, 46]
    prices = baseline_prices + [spike_price]
    volumes = [300] * len(prices)  # volume irrelevant for price test
    return snapshot_factory("PRICE-TEST-1", volumes, prices)


def test_volume_spike_fires_above_threshold() -> None:
    """VolumeSpikeDetector returns DetectionResult when last volume is >> mean."""
    snapshots = _make_volume_snapshots(baseline_vol=300, spike_vol=1500)
    detector = VolumeSpikeDetector(z_threshold=2.5)

    result = detector.detect(snapshots)

    assert result is not None
    assert isinstance(result, DetectionResult)
    assert result.signal_type == "volume_spike"
    assert 0.0 < result.confidence <= 1.0
    assert "z_score" in result.details


def test_volume_no_signal_below_threshold() -> None:
    """VolumeSpikeDetector returns None when all volumes are near the mean."""
    # All volumes nearly equal — z-score will be ~0, far below threshold 2.5
    volumes = [300, 301, 299, 300, 302, 298, 300, 301, 299, 300, 300]
    prices = [50] * len(volumes)
    snapshots = snapshot_factory("VOL-TEST-2", volumes, prices)
    detector = VolumeSpikeDetector(z_threshold=2.5)

    result = detector.detect(snapshots)

    assert result is None


def test_volume_zero_std_guard() -> None:
    """VolumeSpikeDetector returns None (not NaN/crash) when all volumes are identical."""
    volumes = [300] * 61
    prices = [50] * 61
    snapshots = snapshot_factory("VOL-TEST-3", volumes, prices)
    detector = VolumeSpikeDetector(z_threshold=2.5)

    # Must not raise ZeroDivisionError or return NaN confidence
    result = detector.detect(snapshots)

    assert result is None


def test_price_move_fires_above_threshold() -> None:
    """PriceMoveDetector returns DetectionResult when last price far exceeds range."""
    # Baseline range: 45-46 (1 cent spread). Spike: 99. Move pct >> 0.15.
    snapshots = _make_price_snapshots(spike_price=99)
    detector = PriceMoveDetector(move_pct_threshold=0.15)

    result = detector.detect(snapshots)

    assert result is not None
    assert isinstance(result, DetectionResult)
    assert result.signal_type == "price_move"
    assert 0.0 < result.confidence <= 1.0
    assert "move_pct" in result.details


def test_price_move_zero_range_guard() -> None:
    """PriceMoveDetector returns None (not crash) when all prices are identical."""
    prices = [50] * 11
    volumes = [300] * 11
    snapshots = snapshot_factory("PRICE-TEST-2", volumes, prices)
    detector = PriceMoveDetector(move_pct_threshold=0.15)

    # Must not raise ZeroDivisionError
    result = detector.detect(snapshots)

    assert result is None


def test_confidence_clamped() -> None:
    """Confidence is exactly 1.0 for an extreme z-score — never exceeds 1.0."""
    # Extreme spike: 10x baseline should produce z-score >> 2.5
    snapshots = _make_volume_snapshots(baseline_vol=100, spike_vol=100_000)
    detector = VolumeSpikeDetector(z_threshold=2.5)

    result = detector.detect(snapshots)

    assert result is not None
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# TimingClusterDetector tests (SIG-03) — RED: class not yet implemented
# ---------------------------------------------------------------------------


def _make_cluster_snapshots(
    lookback_count: int = 720,
    burst_count: int = 180,
    baseline_vol: int = 10,
    burst_vol: int = 100,
    base_time: datetime | None = None,
) -> list:
    """Build snapshots for TimingClusterDetector testing.

    Args:
        lookback_count: Total number of snapshots to generate.
        burst_count: Number of recent snapshots to assign burst_vol (at the end).
        baseline_vol: Volume assigned to all baseline (non-burst) snapshots.
        burst_vol: Volume assigned to the most recent burst_count snapshots.
        base_time: Base datetime for snapshot timestamps. Defaults to 2025-01-01T12:00:00 UTC.

    Returns:
        List of MagicMock snapshots with .ticker, .volume_24h, .last_price, .captured_at.
        Oldest first, 10-second spacing (consistent with conftest snapshot_factory).
    """
    volumes = [baseline_vol] * (lookback_count - burst_count) + [burst_vol] * burst_count
    prices = [50] * lookback_count
    return snapshot_factory("CLUSTER-TEST-1", volumes, prices, base_time)


def test_timing_cluster_fires_on_burst() -> None:
    """TimingClusterDetector returns DetectionResult when recent volume concentration exceeds threshold.

    Setup: 720 total snapshots — 540 baseline (vol=10) + 180 recent burst (vol=100).
    Volume concentration in the burst window ≈ 180*100 / (540*10 + 180*100) = 18000/23400 ≈ 0.77.
    With cluster_threshold=0.6, concentration > threshold → should fire.
    """
    snapshots = _make_cluster_snapshots(
        lookback_count=720,
        burst_count=180,
        baseline_vol=10,
        burst_vol=100,
    )
    detector = TimingClusterDetector(
        cluster_minutes=30,
        lookback_minutes=120,
        cluster_threshold=0.6,
        min_total_volume=10,
    )

    result = detector.detect(snapshots)

    assert result is not None
    assert isinstance(result, DetectionResult)
    assert result.signal_type == "timing_cluster"
    assert result.confidence > 0.0


def test_timing_cluster_none_on_insufficient_snapshots() -> None:
    """TimingClusterDetector returns None when too few snapshots are provided.

    Only 5 snapshots passed — far below any reasonable min_snapshots guard.
    Detector must return None rather than crash or produce spurious results.
    """
    snapshots = _make_cluster_snapshots(lookback_count=5, burst_count=2)
    detector = TimingClusterDetector(
        cluster_minutes=30,
        lookback_minutes=120,
        cluster_threshold=0.6,
        min_total_volume=10,
    )

    result = detector.detect(snapshots)

    assert result is None


def test_timing_cluster_none_on_dead_market() -> None:
    """TimingClusterDetector returns None when total volume is zero.

    All 720 snapshots have volume_24h=0 → total_volume=0 → division by zero must be guarded.
    Detector must return None (dead market, no meaningful signal).
    """
    snapshots = _make_cluster_snapshots(
        lookback_count=720,
        burst_count=180,
        baseline_vol=0,
        burst_vol=0,
    )
    detector = TimingClusterDetector(
        cluster_minutes=30,
        lookback_minutes=120,
        cluster_threshold=0.6,
        min_total_volume=10,
    )

    result = detector.detect(snapshots)

    assert result is None


def test_timing_cluster_none_on_uniform_volume() -> None:
    """TimingClusterDetector returns None when volume is uniformly distributed.

    720 snapshots all with volume_24h=100 → concentration ≈ lookback_count/lookback_count ratio.
    With cluster_minutes=30 and lookback_minutes=120, the burst window is 1/4 of the lookback.
    Uniform distribution → burst concentration ≈ 0.25, below cluster_threshold=0.6.
    Detector must return None (no anomaly).
    """
    snapshots = _make_cluster_snapshots(
        lookback_count=720,
        burst_count=180,
        baseline_vol=100,
        burst_vol=100,  # same as baseline — uniform volume
    )
    detector = TimingClusterDetector(
        cluster_minutes=30,
        lookback_minutes=120,
        cluster_threshold=0.6,
        min_total_volume=10,
    )

    result = detector.detect(snapshots)

    assert result is None


def test_timing_cluster_confidence_clamped_to_one() -> None:
    """TimingClusterDetector confidence is exactly 1.0 when all volume is in the burst window.

    All 720 snapshots with vol=0 except the last 10 which have vol=1000 (extreme concentration).
    Burst concentration → 1.0; confidence must be clamped to 1.0, not exceed it.
    """
    # 710 dead baseline snapshots + 10 extreme burst snapshots
    volumes = [0] * 710 + [1000] * 10
    prices = [50] * 720
    snapshots = snapshot_factory("CLUSTER-TEST-2", volumes, prices)
    detector = TimingClusterDetector(
        cluster_minutes=30,
        lookback_minutes=120,
        cluster_threshold=0.6,
        min_total_volume=10,
    )

    result = detector.detect(snapshots)

    assert result is not None
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# WinStreakDetector test (SIG-04) — RED: class not yet implemented
# ---------------------------------------------------------------------------


def test_win_streak_always_returns_none() -> None:
    """WinStreakDetector.detect() always returns None — SIG-04 infeasibility stub.

    SIG-04 infeasible — Trade model has no account identifier (SDK v2.0.0).
    The Kalshi Python SDK v2.0.0 Trade model exposes: ticker, count, taker_side,
    yes_price, no_price, trade_id, created_time. No account_id or user_id field
    exists, making per-account win streak computation impossible without private
    API access. WinStreakDetector is a permanent stub that always returns None.
    """
    detector = WinStreakDetector()

    result = detector.detect([])

    assert result is None
