"""Unit tests for growth rate computation utilities.

Validates CAGR calculation edge cases and yearly series building
from XBRL fact tuples.
"""

from __future__ import annotations

import pytest


class TestComputeCAGR:
    """Tests for compute_cagr function."""

    def test_normal_growth(self):
        from ai_washer.analysis.growth import compute_cagr

        # cube root of 2 minus 1 = ~0.2599
        result = compute_cagr(100, 200, 3)
        assert result is not None
        assert abs(result - 0.2599) < 0.001

    def test_zero_start_returns_none(self):
        from ai_washer.analysis.growth import compute_cagr

        result = compute_cagr(0, 200, 3)
        assert result is None

    def test_negative_start_returns_none(self):
        from ai_washer.analysis.growth import compute_cagr

        result = compute_cagr(-50, 200, 3)
        assert result is None

    def test_total_decline_returns_negative_one(self):
        from ai_washer.analysis.growth import compute_cagr

        result = compute_cagr(100, 0, 3)
        assert result == -1.0

    def test_negative_end_returns_negative_one(self):
        from ai_washer.analysis.growth import compute_cagr

        result = compute_cagr(100, -50, 3)
        assert result == -1.0

    def test_zero_years_returns_none(self):
        from ai_washer.analysis.growth import compute_cagr

        result = compute_cagr(100, 100, 0)
        assert result is None

    def test_negative_years_returns_none(self):
        from ai_washer.analysis.growth import compute_cagr

        result = compute_cagr(100, 100, -1)
        assert result is None

    def test_flat_growth_returns_zero(self):
        from ai_washer.analysis.growth import compute_cagr

        result = compute_cagr(100, 100, 3)
        assert result is not None
        assert result == 0.0

    def test_large_growth(self):
        from ai_washer.analysis.growth import compute_cagr

        # 10x over 5 years
        result = compute_cagr(100, 1000, 5)
        assert result is not None
        assert result > 0.5

    def test_decline(self):
        from ai_washer.analysis.growth import compute_cagr

        # Halved over 2 years
        result = compute_cagr(200, 100, 2)
        assert result is not None
        assert result < 0


class TestBuildYearlySeries:
    """Tests for build_yearly_series function."""

    def test_simple_fy_series(self):
        from ai_washer.analysis.growth import build_yearly_series

        facts = [
            (2021, "FY", 100_000),
            (2022, "FY", 150_000),
            (2023, "FY", 200_000),
        ]
        result = build_yearly_series(facts)
        assert result == {2021: 100_000, 2022: 150_000, 2023: 200_000}

    def test_prefers_fy_over_quarterly(self):
        from ai_washer.analysis.growth import build_yearly_series

        facts = [
            (2022, "FY", 500_000),
            (2022, "Q1", 100_000),
            (2022, "Q2", 120_000),
            (2022, "Q3", 130_000),
            (2022, "Q4", 150_000),
        ]
        result = build_yearly_series(facts)
        assert result[2022] == 500_000

    def test_sums_four_quarters_when_no_fy(self):
        from ai_washer.analysis.growth import build_yearly_series

        facts = [
            (2022, "Q1", 100_000),
            (2022, "Q2", 120_000),
            (2022, "Q3", 130_000),
            (2022, "Q4", 150_000),
        ]
        result = build_yearly_series(facts)
        assert result[2022] == 500_000

    def test_max_quarterly_when_not_all_four(self):
        from ai_washer.analysis.growth import build_yearly_series

        facts = [
            (2022, "Q1", 100_000),
            (2022, "Q3", 300_000),
        ]
        result = build_yearly_series(facts)
        assert result[2022] == 300_000

    def test_returns_sorted_dict(self):
        from ai_washer.analysis.growth import build_yearly_series

        facts = [
            (2023, "FY", 300),
            (2021, "FY", 100),
            (2022, "FY", 200),
        ]
        result = build_yearly_series(facts)
        assert list(result.keys()) == [2021, 2022, 2023]

    def test_empty_input(self):
        from ai_washer.analysis.growth import build_yearly_series

        result = build_yearly_series([])
        assert result == {}

    def test_mixed_years(self):
        from ai_washer.analysis.growth import build_yearly_series

        facts = [
            (2021, "FY", 100_000),
            (2022, "Q1", 50_000),
            (2022, "Q2", 60_000),
            (2022, "Q3", 70_000),
            (2022, "Q4", 80_000),
            (2023, "FY", 300_000),
        ]
        result = build_yearly_series(facts)
        assert result[2021] == 100_000
        assert result[2022] == 260_000  # sum of Q1-Q4
        assert result[2023] == 300_000
