"""Sigmoid score normalization.

Maps continuous ratios to bounded 0-100 integer scores using a sigmoid curve.
Used by scoring engines to convert raw signal ratios into comparable scores.

The sigmoid curve ensures:
- ratio = midpoint maps to ~50 (neutral)
- ratio > midpoint maps to 50-100 (more talk than spend = higher risk)
- ratio < midpoint maps to 0-50 (more spend than talk = lower risk)
"""

from __future__ import annotations

import math

# Clamp x to prevent math.exp overflow (exp(710) overflows float64)
_EXP_CLAMP = 500.0


def sigmoid_normalize(
    ratio: float,
    midpoint: float = 1.0,
    steepness: float = 2.0,
    max_score: int = 100,
) -> int:
    """Map a ratio to 0-max_score using a sigmoid curve.

    Args:
        ratio: The input ratio to normalize.
        midpoint: The ratio value that maps to ~50% of max_score.
        steepness: Controls how quickly the curve transitions.
                   Higher values = sharper transition.
        max_score: Maximum output score (default 100).

    Returns:
        Integer score clamped to [0, max_score].
    """
    x = steepness * (ratio - midpoint)

    # Clamp to prevent math.exp overflow
    x = max(-_EXP_CLAMP, min(_EXP_CLAMP, x))

    sigmoid = 1.0 / (1.0 + math.exp(-x))
    raw_score = sigmoid * max_score

    return min(max_score, max(0, round(raw_score)))
