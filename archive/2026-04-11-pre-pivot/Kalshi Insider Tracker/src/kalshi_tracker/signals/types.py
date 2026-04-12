"""Typed domain contracts for signal detection results.

DetectionResult is the immutable output contract from each signal detector.
It flows from detectors -> SignalEngine -> Signal ORM row in the database.
Frozen dataclass enforces fund-wide immutability convention.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionResult:
    """Immutable output from a single signal detector.

    Args:
        signal_type: Detector identifier. Values: 'volume_spike' | 'price_move'.
        confidence: Normalized anomaly score in [0.0, 1.0]. 0.0 = just tripped
            threshold; 1.0 = maximum anomaly. Always clamped — never NaN or >1.
        details: JSON-serializable dict for Signal.details column. Must include
            the raw statistics used to compute confidence (z_score, volume_24h,
            mean, std for volume; move_pct, price_range for price).
    """

    signal_type: str
    confidence: float
    details: dict
