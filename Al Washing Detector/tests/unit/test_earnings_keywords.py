"""Unit tests for earnings-specific keyword lexicons.

Validates EARNINGS_VAGUE_TERMS, EARNINGS_SUBSTANTIVE_TERMS, and
EARNINGS_SECTION_WEIGHTS constants, compile_lexicon integration,
count_keywords_in_text matching, and no overlap between vague/substantive.
"""

from __future__ import annotations


class TestEarningsVagueTerms:
    """Tests for EARNINGS_VAGUE_TERMS constant."""

    def test_is_tuple(self):
        from ai_washer.analysis.keywords import EARNINGS_VAGUE_TERMS

        assert isinstance(EARNINGS_VAGUE_TERMS, tuple)

    def test_min_count(self):
        from ai_washer.analysis.keywords import EARNINGS_VAGUE_TERMS

        assert len(EARNINGS_VAGUE_TERMS) >= 15

    def test_contains_expected_terms(self):
        from ai_washer.analysis.keywords import EARNINGS_VAGUE_TERMS

        for term in ("ai-powered", "leveraging ai", "ai journey"):
            assert term in EARNINGS_VAGUE_TERMS, f"Missing vague term: {term}"


class TestEarningsSubstantiveTerms:
    """Tests for EARNINGS_SUBSTANTIVE_TERMS constant."""

    def test_is_tuple(self):
        from ai_washer.analysis.keywords import EARNINGS_SUBSTANTIVE_TERMS

        assert isinstance(EARNINGS_SUBSTANTIVE_TERMS, tuple)

    def test_min_count(self):
        from ai_washer.analysis.keywords import EARNINGS_SUBSTANTIVE_TERMS

        assert len(EARNINGS_SUBSTANTIVE_TERMS) >= 15

    def test_contains_expected_terms(self):
        from ai_washer.analysis.keywords import EARNINGS_SUBSTANTIVE_TERMS

        for term in ("deployed transformer model", "inference latency", "training pipeline"):
            assert term in EARNINGS_SUBSTANTIVE_TERMS, f"Missing substantive term: {term}"


class TestEarningsLexiconCompilation:
    """Tests for compile_lexicon with earnings terms."""

    def test_earnings_lexicon_compiles(self):
        from ai_washer.analysis.keywords import (
            EARNINGS_SUBSTANTIVE_TERMS,
            EARNINGS_VAGUE_TERMS,
            compile_lexicon,
        )

        patterns = compile_lexicon(EARNINGS_VAGUE_TERMS, EARNINGS_SUBSTANTIVE_TERMS)
        assert isinstance(patterns, list)
        assert len(patterns) == len(EARNINGS_VAGUE_TERMS) + len(EARNINGS_SUBSTANTIVE_TERMS)


class TestEarningsKeywordMatching:
    """Tests for count_keywords_in_text with earnings terms."""

    def test_vague_term_matches(self):
        from ai_washer.analysis.keywords import (
            EARNINGS_SUBSTANTIVE_TERMS,
            EARNINGS_VAGUE_TERMS,
            compile_lexicon,
            count_keywords_in_text,
        )

        patterns = compile_lexicon(EARNINGS_VAGUE_TERMS, EARNINGS_SUBSTANTIVE_TERMS)
        text = "Our AI-powered platform is transforming the industry with AI-powered solutions."
        matches = count_keywords_in_text(text, patterns)
        vague_matches = [m for m in matches if m.tier == "vague"]
        assert any(m.keyword == "ai-powered" for m in vague_matches)

    def test_substantive_term_matches(self):
        from ai_washer.analysis.keywords import (
            EARNINGS_SUBSTANTIVE_TERMS,
            EARNINGS_VAGUE_TERMS,
            compile_lexicon,
            count_keywords_in_text,
        )

        patterns = compile_lexicon(EARNINGS_VAGUE_TERMS, EARNINGS_SUBSTANTIVE_TERMS)
        text = "We have invested in a training pipeline and improved inference latency by 40%."
        matches = count_keywords_in_text(text, patterns)
        substantive_matches = [m for m in matches if m.tier == "substantive"]
        keywords_found = {m.keyword for m in substantive_matches}
        assert "training pipeline" in keywords_found
        assert "inference latency" in keywords_found


class TestEarningsNoOverlap:
    """Tests that vague and substantive earnings terms have no overlap."""

    def test_no_overlap(self):
        from ai_washer.analysis.keywords import (
            EARNINGS_SUBSTANTIVE_TERMS,
            EARNINGS_VAGUE_TERMS,
        )

        vague_set = set(EARNINGS_VAGUE_TERMS)
        substantive_set = set(EARNINGS_SUBSTANTIVE_TERMS)
        overlap = vague_set & substantive_set
        assert len(overlap) == 0, f"Overlapping terms: {overlap}"


class TestEarningsSectionWeights:
    """Tests for EARNINGS_SECTION_WEIGHTS constant."""

    def test_weights_exist(self):
        from ai_washer.analysis.keywords import EARNINGS_SECTION_WEIGHTS

        assert isinstance(EARNINGS_SECTION_WEIGHTS, dict)

    def test_weights_keys(self):
        from ai_washer.analysis.keywords import EARNINGS_SECTION_WEIGHTS

        assert "prepared_remarks" in EARNINGS_SECTION_WEIGHTS
        assert "qa" in EARNINGS_SECTION_WEIGHTS

    def test_weights_values(self):
        from ai_washer.analysis.keywords import EARNINGS_SECTION_WEIGHTS

        assert EARNINGS_SECTION_WEIGHTS["prepared_remarks"] == 0.60
        assert EARNINGS_SECTION_WEIGHTS["qa"] == 0.40
