"""RED tests for VolumeSpikeDetector and PriceMoveDetector (SIG-01, SIG-02).

These tests FAIL on import — kalshi_tracker.signals.detectors does not exist yet.
That is the correct RED state: tests define the interface before implementation.

Test coverage:
  - VolumeSpikeDetector: above threshold, below threshold, zero std guard, confidence clamped
  - PriceMoveDetector: above threshold, zero range guard
"""

from __future__ import annotations

import pytest

# RED: these imports will raise ModuleNotFoundError until Plan 02 is executed.
from kalshi_tracker.signals.detectors import PriceMoveDetector, VolumeSpikeDetector
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
