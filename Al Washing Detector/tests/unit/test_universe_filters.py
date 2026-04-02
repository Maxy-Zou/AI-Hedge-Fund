"""Unit tests for universe filtering and deduplication utilities.

Tests market cap range filtering with boundary values and
CIK-based deduplication with normalization and deterministic sorting.
"""

from __future__ import annotations

import pytest

from ai_washer.universe.filters import deduplicate_by_cik, filter_by_market_cap
from ai_washer.universe.types import EFTSHit, MarketCapRange


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_hit(
    entity_name: str = "TEST CORP",
    ciks: list[str] | None = None,
    accession_no: str = "0000000000-00-000001",
    form_type: str = "10-K",
    file_date: str = "2025-12-01",
) -> EFTSHit:
    """Build a minimal EFTSHit for testing."""
    return EFTSHit(
        accession_no=accession_no,
        form_type=form_type,
        file_date=file_date,
        entity_name=entity_name,
        ciks=ciks or ["12345"],
    )


DEFAULT_RANGE = MarketCapRange(
    min_cents=150_000_000_000,  # $1.5B
    max_cents=900_000_000_000,  # $9B
)


# ---------------------------------------------------------------------------
# filter_by_market_cap tests
# ---------------------------------------------------------------------------


class TestFilterByMarketCap:
    """Tests for the market cap range filter."""

    @pytest.mark.parametrize(
        ("public_float_cents", "expected"),
        [
            (500_000_000_000, True),    # $5B -- within range
            (100_000_000_000, False),   # $1B -- below min
            (1_000_000_000_000, False), # $10B -- above max
            (None, False),             # unknown market cap
            (150_000_000_000, True),    # exactly min boundary -- inclusive
            (900_000_000_000, True),    # exactly max boundary -- inclusive
        ],
        ids=[
            "within_range",
            "below_min",
            "above_max",
            "none_excluded",
            "at_min_boundary",
            "at_max_boundary",
        ],
    )
    def test_filter_by_market_cap(
        self, public_float_cents: int | None, expected: bool
    ) -> None:
        result = filter_by_market_cap(public_float_cents, DEFAULT_RANGE)
        assert result is expected

    def test_custom_range(self) -> None:
        """Filter respects a non-default MarketCapRange."""
        custom = MarketCapRange(min_cents=100, max_cents=500)
        assert filter_by_market_cap(300, custom) is True
        assert filter_by_market_cap(50, custom) is False
        assert filter_by_market_cap(600, custom) is False


# ---------------------------------------------------------------------------
# deduplicate_by_cik tests
# ---------------------------------------------------------------------------


class TestDeduplicateByCik:
    """Tests for CIK-based deduplication of EFTS hits."""

    def test_duplicate_ciks_keeps_first_occurrence(self) -> None:
        """When multiple hits share the same CIK, only the first is kept."""
        hit1 = _make_hit(entity_name="FIRST", ciks=["12345"], file_date="2025-12-01")
        hit2 = _make_hit(entity_name="SECOND", ciks=["12345"], file_date="2025-06-01")
        result = deduplicate_by_cik([hit1, hit2])
        assert len(result) == 1
        assert result[0].entity_name == "FIRST"

    def test_different_ciks_keeps_all(self) -> None:
        """Hits with different CIKs are all preserved."""
        hit1 = _make_hit(entity_name="ALPHA", ciks=["100"])
        hit2 = _make_hit(entity_name="BETA", ciks=["200"])
        hit3 = _make_hit(entity_name="GAMMA", ciks=["300"])
        result = deduplicate_by_cik([hit1, hit2, hit3])
        assert len(result) == 3

    def test_normalizes_cik_format(self) -> None:
        """CIK comparison strips leading zeros before comparing."""
        hit1 = _make_hit(entity_name="PADDED", ciks=["0000012345"])
        hit2 = _make_hit(entity_name="STRIPPED", ciks=["12345"])
        result = deduplicate_by_cik([hit1, hit2])
        assert len(result) == 1

    def test_sorts_by_cik_ascending_for_determinism(self) -> None:
        """Output is sorted by stripped CIK ascending per D-06."""
        hit_a = _make_hit(entity_name="ZZZ", ciks=["300"])
        hit_b = _make_hit(entity_name="AAA", ciks=["100"])
        hit_c = _make_hit(entity_name="MMM", ciks=["200"])
        result = deduplicate_by_cik([hit_a, hit_b, hit_c])
        ciks = [h.ciks[0] for h in result]
        # After stripping: "100", "200", "300" -- sorted ascending
        assert ciks == ["100", "200", "300"]

    def test_empty_list(self) -> None:
        """Empty input returns empty output."""
        result = deduplicate_by_cik([])
        assert result == []

    def test_multi_cik_hit(self) -> None:
        """A hit with multiple CIKs is added once using its first CIK."""
        hit = _make_hit(entity_name="MULTI", ciks=["100", "200"])
        other = _make_hit(entity_name="OTHER", ciks=["200"])
        result = deduplicate_by_cik([hit, other])
        # hit added using CIK "100" first; other uses CIK "200"
        # both CIKs are unique after stripping, so both should be present
        assert len(result) == 2
