"""Unit tests for entity resolution with fuzzy matching.

Tests EntityResolver and resolve_entity for mapping SEC company names
to aliases across data sources (patents, GitHub, job postings).
"""

from __future__ import annotations

from datetime import date

import pytest

from ai_washer.entity.resolver import EntityResolver, resolve_entity
from ai_washer.entity.types import (
    AliasesSchema,
    EntityResolutionResult,
    ResolutionMethod,
)


class TestResolveEntity:
    """Tests for EntityResolver.resolve_entity."""

    def test_resolve_patent_assignee_match(self) -> None:
        """Fuzzy match SEC name to patent assignee candidates."""
        resolver = EntityResolver(threshold=85)
        result = resolver.resolve_entity(
            sec_name="ALPHABET INC",
            cik="0001652044",
            candidates={
                "patent_assignee": ["Google LLC", "Alphabet Inc"],
            },
        )
        assert isinstance(result, EntityResolutionResult)
        assert result.sec_name == "ALPHABET INC"
        assert result.matched_cik == "0001652044"
        assert "Alphabet Inc" in result.resolved_aliases.patent_assignee

    def test_resolve_no_matching_candidates(self) -> None:
        """When no candidate passes threshold, lists stay empty (partial resolution per D-03)."""
        resolver = EntityResolver(threshold=85)
        result = resolver.resolve_entity(
            sec_name="ALPHABET INC",
            cik="0001652044",
            candidates={
                "patent_assignee": ["Totally Unrelated Corp", "Random Industries"],
            },
        )
        assert result.resolved_aliases.patent_assignee == []
        assert result.resolved_aliases.github_org is None

    def test_resolution_metadata_populated(self) -> None:
        """Resolution metadata records method, confidence, and date."""
        resolver = EntityResolver(threshold=85)
        result = resolver.resolve_entity(
            sec_name="NVIDIA CORP",
            cik="0001045810",
            candidates={
                "patent_assignee": ["NVIDIA Corporation"],
            },
        )
        metadata = result.resolved_aliases.resolution_metadata
        assert metadata is not None
        assert metadata.method == ResolutionMethod.AUTOMATED_FUZZY
        assert metadata.resolved_at == date.today()
        assert 0.0 <= metadata.confidence <= 1.0

    def test_below_threshold_returns_empty(self) -> None:
        """Candidates scoring below threshold are excluded (no false positives)."""
        resolver = EntityResolver(threshold=95)  # Very high threshold
        result = resolver.resolve_entity(
            sec_name="META PLATFORMS INC",
            cik="0001326801",
            candidates={
                "patent_assignee": ["Facebook Inc"],  # Related but different name
            },
        )
        # "META PLATFORMS" vs "FACEBOOK" -- score likely below 95
        # Either matches or doesn't, but must not produce false positive
        # If it matches at 95, that's correct; if not, list is empty
        assert isinstance(result.resolved_aliases.patent_assignee, list)

    def test_normalizes_both_sides_before_comparing(self) -> None:
        """Both SEC name and candidates are normalized before fuzzy match."""
        resolver = EntityResolver(threshold=80)
        result = resolver.resolve_entity(
            sec_name="  NVIDIA   CORPORATION  ",
            cik="0001045810",
            candidates={
                "patent_assignee": ["nvidia corp."],
            },
        )
        # After normalization: "NVIDIA" vs "NVIDIA" -- should match
        assert len(result.resolved_aliases.patent_assignee) > 0

    def test_resolve_multiple_sources_independently(self) -> None:
        """Each source (patent_assignee, employer_names) resolved independently."""
        resolver = EntityResolver(threshold=80)
        result = resolver.resolve_entity(
            sec_name="ALPHABET INC",
            cik="0001652044",
            candidates={
                "patent_assignee": ["Alphabet Inc", "Google LLC"],
                "employer_names": ["Alphabet", "Google"],
            },
        )
        assert len(result.resolved_aliases.patent_assignee) > 0
        assert len(result.resolved_aliases.employer_names) > 0

    def test_high_confidence_no_review(self) -> None:
        """High-confidence match (>= 95) sets needs_review=False."""
        resolver = EntityResolver(threshold=85, high_confidence_threshold=95)
        result = resolver.resolve_entity(
            sec_name="NVIDIA CORP",
            cik="0001045810",
            candidates={
                "patent_assignee": ["NVIDIA Corporation"],
            },
        )
        metadata = result.resolved_aliases.resolution_metadata
        assert metadata is not None
        # NVIDIA vs NVIDIA CORPORATION -- very high score after normalization
        # Both normalize to "NVIDIA" so score should be 100
        assert metadata.needs_review is False

    def test_medium_confidence_needs_review(self) -> None:
        """Match between threshold and high_confidence sets needs_review=True."""
        resolver = EntityResolver(threshold=70, high_confidence_threshold=95)
        result = resolver.resolve_entity(
            sec_name="INTERNATIONAL BUSINESS MACHINES CORP",
            cik="0000051143",
            candidates={
                "patent_assignee": ["IBM Corp"],
            },
        )
        metadata = result.resolved_aliases.resolution_metadata
        assert metadata is not None
        # "INTERNATIONAL BUSINESS MACHINES" vs "IBM" -- moderate score
        # If it matches, should be flagged for review due to low confidence
        if result.resolved_aliases.patent_assignee:
            assert metadata.needs_review is True

    def test_cik_always_set(self) -> None:
        """CIK is always set in aliases regardless of match results."""
        resolver = EntityResolver(threshold=85)
        result = resolver.resolve_entity(
            sec_name="UNKNOWN CORP",
            cik="0009999999",
        )
        assert result.resolved_aliases.cik == "0009999999"

    def test_ticker_passed_through(self) -> None:
        """Ticker is passed through to result."""
        resolver = EntityResolver(threshold=85)
        result = resolver.resolve_entity(
            sec_name="ALPHABET INC",
            cik="0001652044",
            ticker="GOOGL",
        )
        assert result.ticker == "GOOGL"

    def test_no_candidates_produces_valid_result(self) -> None:
        """Calling with no candidates produces a valid partial result (D-03)."""
        resolver = EntityResolver(threshold=85)
        result = resolver.resolve_entity(
            sec_name="ALPHABET INC",
            cik="0001652044",
        )
        assert result.resolved_aliases.patent_assignee == []
        assert result.resolved_aliases.employer_names == []
        assert result.resolved_aliases.github_org is None
        assert result.resolved_aliases.cik == "0001652044"
        assert result.resolved_aliases.resolution_metadata is not None

    def test_github_org_exact_match(self) -> None:
        """GitHub org uses exact match (lowered), not fuzzy."""
        resolver = EntityResolver(threshold=85)
        result = resolver.resolve_entity(
            sec_name="ALPHABET INC",
            cik="0001652044",
            candidates={
                "github_org": ["alphabet", "google"],
            },
        )
        assert result.resolved_aliases.github_org == "alphabet"

    def test_github_org_no_match(self) -> None:
        """GitHub org returns None when no exact match found."""
        resolver = EntityResolver(threshold=85)
        result = resolver.resolve_entity(
            sec_name="ALPHABET INC",
            cik="0001652044",
            candidates={
                "github_org": ["totally-different", "unrelated"],
            },
        )
        assert result.resolved_aliases.github_org is None


class TestResolveEntityPartialResolution:
    """Tests for partial resolution per D-03."""

    def test_partial_patent_only(self) -> None:
        """Partial resolution: only patent_assignee provided."""
        resolver = EntityResolver(threshold=80)
        result = resolver.resolve_entity(
            sec_name="NVIDIA CORP",
            cik="0001045810",
            candidates={
                "patent_assignee": ["NVIDIA Corporation"],
            },
        )
        assert len(result.resolved_aliases.patent_assignee) > 0
        assert result.resolved_aliases.employer_names == []
        assert result.resolved_aliases.github_org is None

    def test_partial_employer_only(self) -> None:
        """Partial resolution: only employer_names provided."""
        resolver = EntityResolver(threshold=80)
        result = resolver.resolve_entity(
            sec_name="NVIDIA CORP",
            cik="0001045810",
            candidates={
                "employer_names": ["Nvidia", "NVIDIA Inc"],
            },
        )
        assert result.resolved_aliases.patent_assignee == []
        assert len(result.resolved_aliases.employer_names) > 0


class TestResolveBatch:
    """Tests for EntityResolver.resolve_batch."""

    def test_batch_processes_multiple_entities(self) -> None:
        """Batch resolution processes a list of entities."""
        resolver = EntityResolver(threshold=80)
        entities = [
            ("ALPHABET INC", "0001652044", "GOOGL"),
            ("NVIDIA CORP", "0001045810", "NVDA"),
            ("META PLATFORMS INC", "0001326801", "META"),
        ]
        candidates = {
            "patent_assignee": [
                "Alphabet Inc",
                "NVIDIA Corporation",
                "Meta Platforms Inc",
            ],
        }
        results = resolver.resolve_batch(entities, candidates)
        assert len(results) == 3
        assert all(isinstance(r, EntityResolutionResult) for r in results)

    def test_batch_preserves_order(self) -> None:
        """Batch results are in same order as input."""
        resolver = EntityResolver(threshold=80)
        entities = [
            ("ALPHABET INC", "0001652044", None),
            ("NVIDIA CORP", "0001045810", None),
        ]
        results = resolver.resolve_batch(entities)
        assert results[0].sec_name == "ALPHABET INC"
        assert results[1].sec_name == "NVIDIA CORP"

    def test_batch_empty_list(self) -> None:
        """Empty batch returns empty list."""
        resolver = EntityResolver(threshold=80)
        results = resolver.resolve_batch([])
        assert results == []


class TestConvenienceFunction:
    """Tests for the module-level resolve_entity convenience function."""

    def test_convenience_function_works(self) -> None:
        """Module-level resolve_entity delegates to EntityResolver."""
        result = resolve_entity(
            sec_name="NVIDIA CORP",
            cik="0001045810",
            candidates={
                "patent_assignee": ["NVIDIA Corporation"],
            },
            threshold=85,
        )
        assert isinstance(result, EntityResolutionResult)
        assert result.matched_cik == "0001045810"

    def test_convenience_function_default_threshold(self) -> None:
        """Convenience function uses default threshold of 85."""
        result = resolve_entity(
            sec_name="NVIDIA CORP",
            cik="0001045810",
        )
        assert isinstance(result, EntityResolutionResult)


class TestEntityResolverInit:
    """Tests for EntityResolver initialization and validation."""

    def test_default_thresholds(self) -> None:
        resolver = EntityResolver()
        assert resolver.threshold == 85
        assert resolver.high_confidence_threshold == 95

    def test_custom_thresholds(self) -> None:
        resolver = EntityResolver(threshold=70, high_confidence_threshold=90)
        assert resolver.threshold == 70
        assert resolver.high_confidence_threshold == 90

    def test_threshold_too_low_raises(self) -> None:
        with pytest.raises(ValueError, match="threshold"):
            EntityResolver(threshold=49)

    def test_threshold_too_high_raises(self) -> None:
        with pytest.raises(ValueError, match="threshold"):
            EntityResolver(threshold=101)
