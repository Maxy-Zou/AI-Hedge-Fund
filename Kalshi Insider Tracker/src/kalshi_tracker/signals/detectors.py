"""Signal detectors for Kalshi market anomaly detection.

Four stateless detectors are provided:

VolumeSpikeDetector — z-score on volume_24h over a rolling window.
    Returns DetectionResult when the latest snapshot's volume deviates
    significantly from the baseline mean (z-score > z_threshold).
    Confidence is clamped to [0.0, 1.0].

PriceMoveDetector — percentage move relative to recent price range.
    Returns DetectionResult when the last price moves beyond the recent
    min/max range by more than move_pct_threshold multiples of that range.
    Confidence is clamped to [0.0, 1.0].

TimingClusterDetector — burst volume concentration over a sliding window.
    Returns DetectionResult when the fraction of total trading volume that
    occurred within the most recent cluster_minutes window exceeds
    cluster_threshold. Confidence is scaled linearly above the threshold.
    Returns None when data is insufficient, market is dead, or distribution
    is uniform (SIG-03).

WinStreakDetector — infeasibility stub (SIG-04).
    Always returns None. The Kalshi public API does not expose per-account
    trade history, making win streak computation impossible without private
    API access. Documented as formally infeasible.

All detectors are pure functions wrapped in classes — no DB I/O, no state
mutation, no side effects. They accept any list of objects with .volume_24h,
.last_price, and .captured_at attributes (duck typing, works with ORM rows
and test mocks).
"""

from __future__ import annotations

from datetime import timedelta

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


class TimingClusterDetector:
    """Detect burst volume concentration within a recent time window (SIG-03).

    Algorithm:
        1. Filter snapshots to the lookback window (oldest kept for baseline).
        2. Compute volume deltas (consecutive differences, clamped to 0 for
           reversals) to approximate per-snapshot volume increments.
        3. If total_volume < min_total_volume, return None (dead market).
        4. Compute concentration = recent_volume / total_volume, where
           recent_volume sums deltas from snapshots within cluster_minutes of now.
        5. If concentration <= cluster_threshold, return None (no burst anomaly).
        6. confidence = clamp((concentration - threshold) / (1 - threshold), 0, 1).

    Guards:
        - Returns None if fewer than 12 snapshots in lookback window (min_snapshots).
        - Returns None if total volume delta < min_total_volume (dead market).
        - Returns None if concentration <= cluster_threshold (no anomaly).
    """

    _MIN_SNAPSHOTS: int = 12  # minimum snapshots in lookback window before firing

    def __init__(
        self,
        cluster_minutes: int = 30,
        lookback_minutes: int = 120,
        cluster_threshold: float = 0.6,
        min_total_volume: int = 10,
    ) -> None:
        """Initialize detector with configurable time windows and thresholds.

        Args:
            cluster_minutes: Length of the recent burst window in minutes. Volume
                in this window is compared to the full lookback window. Defaults to 30.
            lookback_minutes: Total lookback window in minutes for baseline volume.
                Defaults to 120.
            cluster_threshold: Minimum concentration ratio [0, 1] to fire a signal.
                Defaults to 0.6.
            min_total_volume: Minimum total volume delta required to produce a signal.
                Markets below this threshold are considered dead. Defaults to 10.
        """
        self.cluster_minutes = cluster_minutes
        self.lookback_minutes = lookback_minutes
        self.cluster_threshold = cluster_threshold
        self.min_total_volume = min_total_volume

    def detect(self, snapshots: list) -> DetectionResult | None:
        """Run timing cluster detection over the provided snapshots.

        Args:
            snapshots: List of objects with .volume_24h and .captured_at attributes.
                Must be ordered oldest first. Must have at least 12 snapshots within
                the lookback window to produce a result.

        Returns:
            DetectionResult with signal_type='timing_cluster' if a burst is detected,
            None otherwise (insufficient data, dead market, or below threshold).
        """
        if not snapshots:
            return None

        now = snapshots[-1].captured_at
        lookback_cutoff = now - timedelta(minutes=self.lookback_minutes)
        cluster_cutoff = now - timedelta(minutes=self.cluster_minutes)

        # Filter to lookback window only
        window_snaps = [s for s in snapshots if s.captured_at >= lookback_cutoff]

        # Guard: need at least min_snapshots to compute meaningful concentration
        if len(window_snaps) < self._MIN_SNAPSHOTS:
            return None

        # Compute volume deltas (consecutive differences, clamp negatives to 0)
        # delta[0] = 0 — no previous snapshot to diff against
        deltas = [0] + [
            max(window_snaps[i].volume_24h - window_snaps[i - 1].volume_24h, 0)
            for i in range(1, len(window_snaps))
        ]

        total_volume = sum(deltas)

        # Guard: dead market — no meaningful volume to analyze
        if total_volume < self.min_total_volume:
            return None

        # Sum deltas for snapshots within the burst window (cluster_minutes of now)
        recent_deltas = [
            deltas[i]
            for i, s in enumerate(window_snaps)
            if s.captured_at >= cluster_cutoff
        ]
        recent_volume = sum(recent_deltas)

        concentration = recent_volume / total_volume

        # Guard: below threshold — no burst anomaly
        if concentration <= self.cluster_threshold:
            return None

        # Scale confidence linearly above the threshold, clamped to [0, 1]
        confidence = float(
            min(
                max(
                    (concentration - self.cluster_threshold) / (1.0 - self.cluster_threshold),
                    0.0,
                ),
                1.0,
            )
        )

        logger.debug(
            "timing_cluster_detected",
            concentration=round(concentration, 4),
            confidence=confidence,
            recent_volume=recent_volume,
            total_volume=total_volume,
        )

        return DetectionResult(
            signal_type="timing_cluster",
            confidence=confidence,
            details={
                "concentration": round(concentration, 4),
                "recent_volume": recent_volume,
                "total_volume": total_volume,
                "cluster_minutes": self.cluster_minutes,
            },
        )


class WinStreakDetector:
    """Win streak signal — INFEASIBLE with Kalshi public API v2.0.0.

    The Kalshi /markets/trades endpoint (MarketsApi.get_trades) returns
    anonymized Trade objects. Complete field list from SDK v2.0.0:
      trade_id, ticker, price, count, taker_side, created_time
    No user_id, account_id, member_id, or trader_id field exists.

    The /portfolio/fills endpoint (PortfolioApi.get_fills) returns fills for
    the authenticated user only — it cannot query another account's activity.

    No public leaderboard or per-account trade history endpoint exists in
    any API module: markets_api, portfolio_api, events_api, exchange_api,
    series_api, milestones_api.

    This stub satisfies SIG-04's success criterion: "formally documented as
    infeasible with API evidence." It is NOT registered in SignalEngine.

    Source: .venv/lib/python3.13/site-packages/kalshi_python/models/trade.py
    """

    def detect(self, snapshots: list) -> DetectionResult | None:
        """Always returns None — win streak detection is infeasible."""
        return None
