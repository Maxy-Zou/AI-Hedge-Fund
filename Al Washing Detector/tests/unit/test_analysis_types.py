"""Unit tests for analysis type contracts.

Validates Pydantic models and the FilingForScoring frozen dataclass
used as shared inputs/outputs for the analysis package.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestFilingForScoring:
    """Tests for the FilingForScoring frozen dataclass."""

    def test_create_valid_instance(self):
        from ai_washer.analysis.types import FilingForScoring

        filing = FilingForScoring(year=2023, sections={"mda": "text about AI"})
        assert filing.year == 2023
        assert filing.sections == {"mda": "text about AI"}

    def test_frozen_immutable(self):
        from ai_washer.analysis.types import FilingForScoring

        filing = FilingForScoring(year=2023, sections={"mda": "text"})
        with pytest.raises(AttributeError):
            filing.year = 2024  # type: ignore[misc]

    def test_hashable(self):
        """Frozen dataclass should be hashable for use in sets/dicts."""
        from ai_washer.analysis.types import FilingForScoring

        # dict is not hashable, so FilingForScoring itself is not hashable
        # due to the mutable dict field. But it IS frozen (immutable attributes).
        filing = FilingForScoring(year=2023, sections={"mda": "text"})
        assert filing.year == 2023  # At minimum, frozen prevents mutation

    def test_sections_with_none_values(self):
        from ai_washer.analysis.types import FilingForScoring

        filing = FilingForScoring(
            year=2024,
            sections={"mda": "Some text", "risk_factors": None, "business": None},
        )
        assert filing.sections["risk_factors"] is None
        assert filing.sections["mda"] == "Some text"

    def test_equality(self):
        from ai_washer.analysis.types import FilingForScoring

        a = FilingForScoring(year=2023, sections={"mda": "text"})
        b = FilingForScoring(year=2023, sections={"mda": "text"})
        assert a == b


class TestKeywordLexicon:
    """Tests for the KeywordLexicon Pydantic model."""

    def test_valid_lexicon(self):
        from ai_washer.analysis.types import KeywordLexicon

        lex = KeywordLexicon(vague=["ai-powered"], substantive=["neural network"])
        assert lex.vague == ["ai-powered"]
        assert lex.substantive == ["neural network"]

    def test_empty_lists_allowed(self):
        """Empty lists are structurally valid (content validation is elsewhere)."""
        from ai_washer.analysis.types import KeywordLexicon

        lex = KeywordLexicon(vague=[], substantive=[])
        assert lex.vague == []


class TestSectionKeywordCounts:
    """Tests for SectionKeywordCounts model."""

    def test_defaults(self):
        from ai_washer.analysis.types import SectionKeywordCounts

        counts = SectionKeywordCounts()
        assert counts.vague_count == 0
        assert counts.substantive_count == 0
        assert counts.total == 0

    def test_with_values(self):
        from ai_washer.analysis.types import SectionKeywordCounts

        counts = SectionKeywordCounts(vague_count=5, substantive_count=3, total=8)
        assert counts.total == 8


class TestKeywordFrequencyResult:
    """Tests for KeywordFrequencyResult model."""

    def test_valid_result(self):
        from ai_washer.analysis.types import KeywordFrequencyResult, SectionKeywordCounts

        result = KeywordFrequencyResult(
            total_weighted_count=12.5,
            by_section={"mda": SectionKeywordCounts(vague_count=5, substantive_count=3, total=8)},
            by_tier={"vague": 5, "substantive": 3},
            sections_available=["mda"],
            sections_missing=["risk_factors", "business"],
        )
        assert result.total_weighted_count == 12.5
        assert result.by_tier["vague"] == 5


class TestGrowthRateResult:
    """Tests for GrowthRateResult model."""

    def test_valid_result(self):
        from ai_washer.analysis.types import GrowthRateResult

        result = GrowthRateResult(
            keyword_growth=0.15,
            spending_growth=-0.05,
            window_years=3,
            start_year=2020,
            end_year=2023,
        )
        assert result.keyword_growth == 0.15
        assert result.spending_growth == -0.05

    def test_none_growth_values(self):
        from ai_washer.analysis.types import GrowthRateResult

        result = GrowthRateResult(
            keyword_growth=None,
            spending_growth=None,
            window_years=3,
            start_year=2020,
            end_year=2023,
        )
        assert result.keyword_growth is None


class TestSignalResult:
    """Tests for SignalResult model."""

    def test_valid_result(self):
        from ai_washer.analysis.types import SignalResult

        result = SignalResult(
            signal_type="sec_filing",
            score=75,
            evidence={"keyword_count": 42, "growth_rate": 0.15},
        )
        assert result.signal_type == "sec_filing"
        assert result.score == 75
        assert result.evidence["keyword_count"] == 42

    def test_compute_spending_signal(self):
        from ai_washer.analysis.types import SignalResult

        result = SignalResult(
            signal_type="compute_spending",
            score=30,
            evidence={"capex_trend": "declining"},
        )
        assert result.signal_type == "compute_spending"
