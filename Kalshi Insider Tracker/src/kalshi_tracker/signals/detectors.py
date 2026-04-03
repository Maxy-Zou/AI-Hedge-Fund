"""Signal detectors for Kalshi market anomaly detection.

Two stateless detectors are provided:

VolumeSpikeDetector — z-score on volume_24h over a rolling window.
    Returns DetectionResult when the latest snapshot's volume deviates
    significantly from the baseline mean (z-score > z_threshold).
    Confidence is clamped to [0.0, 1.0].

PriceMoveDetector — percentage move relative to recent price range.
    Returns DetectionResult when the last price moves beyond the recent
    min/max range by more than move_pct_threshold multiples of that range.
    Confidence is clamped to [0.0, 1.0].

Both detectors are pure functions wrapped in classes — no DB I/O, no state
mutation, no side effects. They accept any list of objects with .volume_24h
and .last_price attributes (duck typing, works with ORM rows and test mocks).
"""

from __future__ import annotations

import numpy as np
import structlog

from kalshi_tracker.signals.types import DetectionResult

logger = structlog.get_logger(__name__)


class VolumeSpikeDetector:
    """Detect volume spikes using z-score over a rolling baseline window.

    Z-score formula:
        arr = volume_24h values from last `window` snapshots
        baseline = arr[:-1] (all but the most recent)
        current = arr[-1]
        std = baseline.std()
        z_score = (current - baseline.mean()) / std  if std > 0 else 0

    Confidence formula:
        confidence = clamp((z_score - z_threshold) / z_threshold, 0.0, 1.0)

    Guards:
        - Returns None if insufficient snapshots (< window)
        - Returns None if std == 0 (flat/thin market — no meaningful z-score)
        - Returns None if z_score <= z_threshold (no anomaly)
    """

    def __init__(self, z_threshold: float = 2.5, window: int = 60) -> None:
        """Initialize detector with configurable threshold and window size.

        Args:
            z_threshold: Minimum z-score to trigger a detection. Defaults to 2.5.
            window: Number of snapshots to use for rolling baseline. Defaults to 60.
        """
        self.z_threshold = z_threshold
        self.window = window

    def detect(self, snapshots: list) -> DetectionResult | None:
        """Run volume spike detection over the provided snapshots.

        Args:
            snapshots: List of objects with .volume_24h attribute. Most recent
                snapshot is last. Must have at least `window` elements.

        Returns:
            DetectionResult with signal_type='volume_spike' if a spike is detected,
            None otherwise (insufficient data, zero std, or below threshold).
        """
        volumes = [s.volume_24h for s in snapshots]

        # Need at least window baseline points + 1 current point.
        if len(volumes) < self.window + 1:
            return None

        # Use the last window+1 elements: window baseline points + 1 current.
        arr = np.array(volumes[-(self.window + 1):], dtype=float)
        baseline = arr[:-1]
        current = arr[-1]

        mean = float(baseline.mean())
        std = float(baseline.std())

        if std == 0.0:
            # Flat baseline — no z-score possible. Only return None if current
            # also equals the baseline (no spike). If current differs, it is an
            # extreme anomaly (effectively infinite z-score); clamp confidence to 1.0.
            # Use a large sentinel z_score value for the details dict (JSON-safe).
            if current == mean:
                return None
            z_score = 999.0  # sentinel: infinite z-score, baseline was flat
            confidence = 1.0
        else:
            z_score = float((current - mean) / std)
            if z_score <= self.z_threshold:
                return None
            confidence = float(min(max((z_score - self.z_threshold) / self.z_threshold, 0.0), 1.0))

        logger.debug(
            "volume_spike_detected",
            z_score=round(z_score, 4),
            confidence=confidence,
            volume_24h=int(current),
        )

        return DetectionResult(
            signal_type="volume_spike",
            confidence=confidence,
            details={
                "z_score": round(z_score, 4),
                "volume_24h": int(current),
                "mean": round(mean, 2),
                "std": round(std, 2),
            },
        )


class PriceMoveDetector:
    """Detect sharp price moves relative to the recent price range.

    Price move formula:
        prices = last_price values from last min(window, len) snapshots
        recent = prices[:-1] (baseline range, excludes current tick)
        current = prices[-1]
        prev = prices[-2]
        price_range = max(recent) - min(recent)
        move = abs(current - prev)
        move_pct = move / price_range  if price_range > 0 else 0

    Confidence formula:
        confidence = clamp(move_pct / move_pct_threshold, 0.0, 1.0)

    Guards:
        - Returns None if fewer than 2 snapshots (cannot compute a move)
        - Returns None if price_range == 0 (flat market — no meaningful reference range)
        - Returns None if move_pct <= move_pct_threshold (no anomaly)
    """

    def __init__(self, move_pct_threshold: float = 0.15, window: int = 60) -> None:
        """Initialize detector with configurable threshold and window size.

        Args:
            move_pct_threshold: Minimum price move (as multiple of price range) to
                trigger detection. Defaults to 0.15.
            window: Max snapshots to use for price range baseline. Defaults to 60.
        """
        self.move_pct_threshold = move_pct_threshold
        self.window = window

    def detect(self, snapshots: list) -> DetectionResult | None:
        """Run price move detection over the provided snapshots.

        Args:
            snapshots: List of objects with .last_price attribute. Most recent
                snapshot is last. Must have at least 2 elements.

        Returns:
            DetectionResult with signal_type='price_move' if a move is detected,
            None otherwise (insufficient data, zero range, or below threshold).
        """
        if len(snapshots) < 2:
            return None

        prices = [s.last_price for s in snapshots]
        used = prices[-min(self.window, len(prices)):]

        current = used[-1]
        prev = used[-2]
        recent = used[:-1]

        price_range = max(recent) - min(recent)
        if price_range == 0:
            return None

        move = abs(current - prev)
        move_pct = move / price_range

        if move_pct <= self.move_pct_threshold:
            return None

        confidence = float(min(move_pct / self.move_pct_threshold, 1.0))

        logger.debug(
            "price_move_detected",
            move_pct=round(move_pct, 4),
            confidence=confidence,
            last_price=current,
        )

        return DetectionResult(
            signal_type="price_move",
            confidence=confidence,
            details={
                "move_pct": round(move_pct, 4),
                "price_range": price_range,
                "last_price": current,
                "prev_price": prev,
            },
        )
