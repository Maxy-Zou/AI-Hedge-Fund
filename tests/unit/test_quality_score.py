"""Tests for compute_quality_score -- pure-function weighted mean aggregator.

These tests verify the DEBATE-04 tool-first enforcement: the aggregation
of the three LLM-produced sub-scores into a single quality_score is done
by deterministic Python (not the LLM).

CLAUDE.md: "Tool-first for quantitative work. LLMs NEVER compute financial
ratios, run backtests, or calculate position sizes directly." Weighted-mean
aggregation IS a quantitative computation -- so the weights and the
arithmetic must be Python code, not prompt instructions.

``compute_quality_score`` itself is a plain function with no Agent, no
network, and no I/O -- but importing the ``debate_synthesis`` module
constructs ``debate_synthesis_agent`` at module load time, which requires
ANTHROPIC_API_KEY to satisfy the PydanticAI Anthropic provider factory.
The dummy-key setup below matches the pattern used by every other
Phase-4/5 agent test file.
"""

from __future__ import annotations

import os

# Set dummy API key before importing the module (the module constructs
# debate_synthesis_agent at import time, which triggers PydanticAI's
# Anthropic provider factory; it needs ANTHROPIC_API_KEY to be set).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pytest  # noqa: E402

from ai_hedge_fund.agents.debate_synthesis import (  # noqa: E402
    EVIDENCE_WEIGHT,
    LOGIC_WEIGHT,
    RISK_WEIGHT,
    compute_quality_score,
)


class TestWeightConstants:
    """Tests for the module-level quality-score weight constants."""

    def test_weights_sum_to_one(self) -> None:
        """The three weights must sum to exactly 1.0 (within float epsilon)."""
        assert abs(EVIDENCE_WEIGHT + LOGIC_WEIGHT + RISK_WEIGHT - 1.0) < 1e-9

    def test_evidence_is_dominant(self) -> None:
        """evidence_strength carries the largest weight per RESEARCH.md A1."""
        assert EVIDENCE_WEIGHT >= LOGIC_WEIGHT
        assert EVIDENCE_WEIGHT >= RISK_WEIGHT


class TestComputeQualityScore:
    """Tests for compute_quality_score() arithmetic and range enforcement."""

    def test_all_zero(self) -> None:
        """All sub-scores at 0 yield a quality_score of 0."""
        assert compute_quality_score(0, 0, 0) == 0

    def test_all_hundred(self) -> None:
        """All sub-scores at 100 yield a quality_score of 100."""
        assert compute_quality_score(100, 100, 100) == 100

    def test_weighted_mean_balanced(self) -> None:
        """Documented example: 0.4*80 + 0.3*60 + 0.3*40 = 62.0 -> 62."""
        assert compute_quality_score(80, 60, 40) == 62

    def test_evidence_only(self) -> None:
        """Evidence-only (100/0/0) yields 0.4*100 = 40."""
        assert compute_quality_score(100, 0, 0) == 40

    def test_logic_only(self) -> None:
        """Logic-only (0/100/0) yields 0.3*100 = 30."""
        assert compute_quality_score(0, 100, 0) == 30

    def test_risk_only(self) -> None:
        """Risk-only (0/0/100) yields 0.3*100 = 30."""
        assert compute_quality_score(0, 0, 100) == 30

    def test_rounding_half_up(self) -> None:
        """Equal sub-scores pass through unchanged (0.4*55 + 0.3*55 + 0.3*55 = 55.0)."""
        assert compute_quality_score(55, 55, 55) == 55

    def test_rejects_negative_evidence(self) -> None:
        """Negative evidence_strength raises ValueError."""
        with pytest.raises(ValueError):
            compute_quality_score(-1, 50, 50)

    def test_rejects_over_hundred_evidence(self) -> None:
        """evidence_strength > 100 raises ValueError."""
        with pytest.raises(ValueError):
            compute_quality_score(101, 50, 50)

    def test_rejects_negative_logic(self) -> None:
        """Negative logical_consistency raises ValueError."""
        with pytest.raises(ValueError):
            compute_quality_score(50, -1, 50)

    def test_rejects_over_hundred_logic(self) -> None:
        """logical_consistency > 100 raises ValueError."""
        with pytest.raises(ValueError):
            compute_quality_score(50, 101, 50)

    def test_rejects_negative_risk(self) -> None:
        """Negative risk_coverage raises ValueError."""
        with pytest.raises(ValueError):
            compute_quality_score(50, 50, -1)

    def test_rejects_over_hundred_risk(self) -> None:
        """risk_coverage > 100 raises ValueError."""
        with pytest.raises(ValueError):
            compute_quality_score(50, 50, 101)
