"""Unit tests for sigmoid score normalization.

Validates that the sigmoid function maps ratios to deterministic,
bounded 0-100 integer scores.
"""

from __future__ import annotations

import pytest


class TestSigmoidNormalize:
    """Tests for sigmoid_normalize function."""

    def test_midpoint_returns_50(self):
        from ai_washer.analysis.normalization import sigmoid_normalize

        result = sigmoid_normalize(ratio=1.0, midpoint=1.0, steepness=2.0)
        assert result == 50

    def test_high_ratio_returns_above_90(self):
        from ai_washer.analysis.normalization import sigmoid_normalize

        result = sigmoid_normalize(ratio=3.0, midpoint=1.0, steepness=2.0)
        assert result > 90

    def test_low_ratio_returns_below_20(self):
        from ai_washer.analysis.normalization import sigmoid_normalize

        result = sigmoid_normalize(ratio=0.0, midpoint=1.0, steepness=2.0)
        assert result < 20

    def test_returns_integer(self):
        from ai_washer.analysis.normalization import sigmoid_normalize

        result = sigmoid_normalize(ratio=1.5, midpoint=1.0, steepness=2.0)
        assert isinstance(result, int)

    def test_always_in_range_0_100(self):
        from ai_washer.analysis.normalization import sigmoid_normalize

        for ratio in [-10, -1, 0, 0.5, 1.0, 2.0, 5.0, 100.0, 1000.0]:
            result = sigmoid_normalize(ratio=ratio, midpoint=1.0, steepness=2.0)
            assert 0 <= result <= 100, f"Out of range for ratio={ratio}: {result}"

    def test_deterministic_same_input_same_output(self):
        from ai_washer.analysis.normalization import sigmoid_normalize

        results = [
            sigmoid_normalize(ratio=1.5, midpoint=1.0, steepness=2.0)
            for _ in range(100)
        ]
        assert len(set(results)) == 1, "Non-deterministic results"

    def test_negative_ratio_below_50(self):
        from ai_washer.analysis.normalization import sigmoid_normalize

        result = sigmoid_normalize(ratio=-1.0, midpoint=1.0, steepness=2.0)
        assert result < 50

    def test_very_large_ratio_does_not_overflow(self):
        from ai_washer.analysis.normalization import sigmoid_normalize

        # Should not raise OverflowError
        result = sigmoid_normalize(ratio=1000.0, midpoint=1.0, steepness=2.0)
        assert result == 100

    def test_very_negative_ratio_does_not_overflow(self):
        from ai_washer.analysis.normalization import sigmoid_normalize

        # Should not raise OverflowError
        result = sigmoid_normalize(ratio=-1000.0, midpoint=1.0, steepness=2.0)
        assert result == 0

    def test_custom_max_score(self):
        from ai_washer.analysis.normalization import sigmoid_normalize

        result = sigmoid_normalize(ratio=1.0, midpoint=1.0, steepness=2.0, max_score=50)
        assert result == 25  # midpoint maps to half of max_score

    def test_monotonically_increasing(self):
        """Higher ratio should produce higher or equal score."""
        from ai_washer.analysis.normalization import sigmoid_normalize

        prev = 0
        for ratio in [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]:
            score = sigmoid_normalize(ratio=ratio, midpoint=1.0, steepness=2.0)
            assert score >= prev, f"Not monotonic at ratio={ratio}"
            prev = score
