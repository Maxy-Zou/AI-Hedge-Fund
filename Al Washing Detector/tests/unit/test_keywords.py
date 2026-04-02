"""Unit tests for keyword lexicon and counting logic.

Validates two-tier keyword classification, word boundary matching,
section-weighted frequency computation, and cloud/compute keyword detection.
"""

from __future__ import annotations

import re

import pytest


class TestKeywordConstants:
    """Tests for module-level keyword tuple constants."""

    def test_vague_buzzwords_is_tuple(self):
        from ai_washer.analysis.keywords import VAGUE_BUZZWORDS

        assert isinstance(VAGUE_BUZZWORDS, tuple)

    def test_vague_buzzwords_min_count(self):
        from ai_washer.analysis.keywords import VAGUE_BUZZWORDS

        assert len(VAGUE_BUZZWORDS) >= 20

    def test_vague_buzzwords_contains_expected(self):
        from ai_washer.analysis.keywords import VAGUE_BUZZWORDS

        for term in ("ai-powered", "leveraging ai", "ai capabilities"):
            assert term in VAGUE_BUZZWORDS, f"Missing vague term: {term}"

    def test_substantive_terms_is_tuple(self):
        from ai_washer.analysis.keywords import SUBSTANTIVE_TERMS

        assert isinstance(SUBSTANTIVE_TERMS, tuple)

    def test_substantive_terms_min_count(self):
        from ai_washer.analysis.keywords import SUBSTANTIVE_TERMS

        assert len(SUBSTANTIVE_TERMS) >= 20

    def test_substantive_terms_contains_expected(self):
        from ai_washer.analysis.keywords import SUBSTANTIVE_TERMS

        for term in ("neural network", "model training", "inference latency"):
            assert term in SUBSTANTIVE_TERMS, f"Missing substantive term: {term}"

    def test_cloud_compute_keywords_is_tuple(self):
        from ai_washer.analysis.keywords import CLOUD_COMPUTE_KEYWORDS

        assert isinstance(CLOUD_COMPUTE_KEYWORDS, tuple)

    def test_cloud_compute_keywords_contains_expected(self):
        from ai_washer.analysis.keywords import CLOUD_COMPUTE_KEYWORDS

        for term in ("aws", "azure", "google cloud", "nvidia", "gpu", "cloud computing"):
            assert term in CLOUD_COMPUTE_KEYWORDS, f"Missing cloud term: {term}"

    def test_default_section_weights(self):
        from ai_washer.analysis.keywords import DEFAULT_SECTION_WEIGHTS

        assert DEFAULT_SECTION_WEIGHTS == {"mda": 0.50, "risk_factors": 0.20, "business": 0.30}


class TestCompileLexicon:
    """Tests for compile_lexicon function."""

    def test_returns_list_of_tuples(self):
        from ai_washer.analysis.keywords import compile_lexicon

        patterns = compile_lexicon(("ai-powered",), ("neural network",))
        assert isinstance(patterns, list)
        assert len(patterns) == 2
        # Each item is (compiled_pattern, keyword_str, tier_str)
        pattern, keyword, tier = patterns[0]
        assert isinstance(pattern, re.Pattern)
        assert isinstance(keyword, str)
        assert isinstance(tier, str)

    def test_word_boundary_ai_not_in_fair(self):
        """Pitfall 3: 'AI' must not match inside 'FAIR' or 'MAINTAIN'."""
        from ai_washer.analysis.keywords import compile_lexicon

        patterns = compile_lexicon(("ai",), ())
        pattern, _, _ = patterns[0]
        # Should match standalone "AI"
        assert pattern.findall("AI is powerful") == ["AI"]
        # Should NOT match inside other words
        assert pattern.findall("FAIR") == []
        assert pattern.findall("MAINTAIN") == []
        assert pattern.findall("BRAIN") == []

    def test_word_boundary_hyphenated_term(self):
        """Hyphenated terms like 'ai-powered' should match correctly."""
        from ai_washer.analysis.keywords import compile_lexicon

        patterns = compile_lexicon(("ai-powered",), ())
        pattern, _, _ = patterns[0]
        assert len(pattern.findall("Our ai-powered solution")) == 1
        assert len(pattern.findall("No match here")) == 0

    def test_case_insensitive(self):
        from ai_washer.analysis.keywords import compile_lexicon

        patterns = compile_lexicon(("neural network",), ())
        pattern, _, _ = patterns[0]
        assert len(pattern.findall("Neural Network")) == 1
        assert len(pattern.findall("NEURAL NETWORK")) == 1
        assert len(pattern.findall("neural network")) == 1

    def test_tier_labels(self):
        from ai_washer.analysis.keywords import compile_lexicon

        patterns = compile_lexicon(("buzzword",), ("technical",))
        tiers = [(kw, tier) for _, kw, tier in patterns]
        assert ("buzzword", "vague") in tiers
        assert ("technical", "substantive") in tiers


class TestCountKeywordsInText:
    """Tests for count_keywords_in_text function."""

    def test_empty_string_returns_empty(self):
        from ai_washer.analysis.keywords import compile_lexicon, count_keywords_in_text

        patterns = compile_lexicon(("ai",), ("neural network",))
        result = count_keywords_in_text("", patterns)
        assert result == []

    def test_counts_multiple_occurrences(self):
        from ai_washer.analysis.keywords import compile_lexicon, count_keywords_in_text

        patterns = compile_lexicon(("ai",), ())
        text = "AI is great. AI powers everything. AI AI AI."
        result = count_keywords_in_text(text, patterns)
        assert len(result) == 1
        match = result[0]
        assert match.keyword == "ai"
        assert match.tier == "vague"
        assert match.count == 5

    def test_returns_only_matches_with_count_gt_zero(self):
        from ai_washer.analysis.keywords import compile_lexicon, count_keywords_in_text

        patterns = compile_lexicon(("ai", "quantum computing"), ("neural network",))
        text = "AI is mentioned here, no other terms present."
        result = count_keywords_in_text(text, patterns)
        keywords_found = {m.keyword for m in result}
        assert "ai" in keywords_found
        # "quantum computing" has zero matches -- should not appear
        assert "quantum computing" not in keywords_found
        # "neural network" also not in text
        assert "neural network" not in keywords_found

    def test_keyword_match_is_frozen(self):
        from ai_washer.analysis.keywords import compile_lexicon, count_keywords_in_text

        patterns = compile_lexicon(("ai",), ())
        result = count_keywords_in_text("AI here", patterns)
        match = result[0]
        with pytest.raises(AttributeError):
            match.count = 999  # type: ignore[misc]


class TestComputeSectionWeightedFrequency:
    """Tests for compute_section_weighted_frequency."""

    def test_basic_weighted_frequency(self):
        from ai_washer.analysis.keywords import (
            compile_lexicon,
            compute_section_weighted_frequency,
        )

        patterns = compile_lexicon(("ai",), ("neural network",))
        # MD&A weight 0.50, risk_factors 0.20, business 0.30
        sections = {
            "mda": "AI " * 200 + " filler " * 100,  # > 500 chars, 200 AI mentions
            "risk_factors": "AI " * 100 + " filler " * 100,  # > 500 chars, 100 AI mentions
            "business": "AI " * 50 + " filler " * 100,  # > 500 chars, 50 AI mentions
        }
        result = compute_section_weighted_frequency(sections, patterns)
        assert result.total_weighted_count > 0
        assert "mda" in result.by_section
        assert "risk_factors" in result.by_section
        assert "business" in result.by_section
        assert result.sections_missing == []
        assert sorted(result.sections_available) == ["business", "mda", "risk_factors"]

    def test_skips_none_sections(self):
        from ai_washer.analysis.keywords import (
            compile_lexicon,
            compute_section_weighted_frequency,
        )

        patterns = compile_lexicon(("ai",), ())
        sections = {
            "mda": "AI " * 200 + " filler " * 100,  # > 500 chars
            "risk_factors": None,
            "business": None,
        }
        result = compute_section_weighted_frequency(sections, patterns)
        assert "risk_factors" in result.sections_missing
        assert "business" in result.sections_missing
        assert result.sections_available == ["mda"]
        # With only mda available, all weight goes to mda (renormalized to 1.0)
        assert result.total_weighted_count > 0

    def test_skips_short_sections(self):
        """Sections under 500 chars should be treated as missing (per Phase 3 rule)."""
        from ai_washer.analysis.keywords import (
            compile_lexicon,
            compute_section_weighted_frequency,
        )

        patterns = compile_lexicon(("ai",), ())
        sections = {
            "mda": "AI " * 200 + " filler " * 100,  # > 500 chars
            "risk_factors": "AI short",  # < 500 chars
            "business": "AI " * 200 + " filler " * 100,  # > 500 chars
        }
        result = compute_section_weighted_frequency(sections, patterns)
        assert "risk_factors" in result.sections_missing
        assert "risk_factors" not in result.sections_available

    def test_all_sections_missing_returns_zero(self):
        from ai_washer.analysis.keywords import (
            compile_lexicon,
            compute_section_weighted_frequency,
        )

        patterns = compile_lexicon(("ai",), ())
        sections: dict[str, str | None] = {
            "mda": None,
            "risk_factors": None,
            "business": None,
        }
        result = compute_section_weighted_frequency(sections, patterns)
        assert result.total_weighted_count == 0.0
        assert len(result.sections_available) == 0

    def test_custom_section_weights(self):
        from ai_washer.analysis.keywords import (
            compile_lexicon,
            compute_section_weighted_frequency,
        )

        patterns = compile_lexicon(("ai",), ())
        sections = {
            "mda": "AI " * 200 + " filler " * 100,
            "risk_factors": "AI " * 200 + " filler " * 100,
            "business": "AI " * 200 + " filler " * 100,
        }
        custom_weights = {"mda": 0.80, "risk_factors": 0.10, "business": 0.10}
        result = compute_section_weighted_frequency(sections, patterns, section_weights=custom_weights)
        assert result.total_weighted_count > 0

    def test_by_tier_aggregation(self):
        from ai_washer.analysis.keywords import (
            compile_lexicon,
            compute_section_weighted_frequency,
        )

        patterns = compile_lexicon(("ai",), ("neural network",))
        text = "AI AI AI neural network neural network " + " filler" * 100
        sections = {"mda": text, "risk_factors": None, "business": None}
        result = compute_section_weighted_frequency(sections, patterns)
        assert result.by_tier["vague"] == 3
        assert result.by_tier["substantive"] == 2


class TestCloudComputeKeywords:
    """Tests for cloud/compute keyword detection."""

    def test_cloud_keywords_detected_in_text(self):
        from ai_washer.analysis.keywords import CLOUD_COMPUTE_KEYWORDS, compile_lexicon, count_keywords_in_text

        patterns = compile_lexicon((), CLOUD_COMPUTE_KEYWORDS)
        text = "We use AWS and Azure for our GPU workloads with Nvidia chips."
        result = count_keywords_in_text(text, patterns)
        keywords_found = {m.keyword for m in result}
        assert "aws" in keywords_found
        assert "azure" in keywords_found
        assert "gpu" in keywords_found
        assert "nvidia" in keywords_found
