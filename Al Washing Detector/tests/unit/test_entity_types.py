"""Tests for entity resolution Pydantic type contracts."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError


class TestResolutionMethod:
    """Tests for ResolutionMethod enum."""

    def test_automated_fuzzy_value(self):
        from ai_washer.entity.types import ResolutionMethod

        assert ResolutionMethod.AUTOMATED_FUZZY == "automated_fuzzy"

    def test_manual_seed_value(self):
        from ai_washer.entity.types import ResolutionMethod

        assert ResolutionMethod.MANUAL_SEED == "manual_seed"

    def test_manual_override_value(self):
        from ai_washer.entity.types import ResolutionMethod

        assert ResolutionMethod.MANUAL_OVERRIDE == "manual_override"

    def test_is_str_enum(self):
        from ai_washer.entity.types import ResolutionMethod

        assert isinstance(ResolutionMethod.AUTOMATED_FUZZY, str)


class TestResolutionMetadata:
    """Tests for ResolutionMetadata Pydantic model."""

    def test_valid_metadata(self):
        from ai_washer.entity.types import ResolutionMetadata, ResolutionMethod

        meta = ResolutionMetadata(
            resolved_at=date(2026, 3, 27),
            method=ResolutionMethod.AUTOMATED_FUZZY,
            confidence=0.92,
            needs_review=False,
        )
        assert meta.resolved_at == date(2026, 3, 27)
        assert meta.method == "automated_fuzzy"
        assert meta.confidence == 0.92
        assert meta.needs_review is False

    def test_confidence_bounds_zero(self):
        from ai_washer.entity.types import ResolutionMetadata, ResolutionMethod

        meta = ResolutionMetadata(
            resolved_at=date(2026, 1, 1),
            method=ResolutionMethod.MANUAL_SEED,
            confidence=0.0,
        )
        assert meta.confidence == 0.0

    def test_confidence_bounds_one(self):
        from ai_washer.entity.types import ResolutionMetadata, ResolutionMethod

        meta = ResolutionMetadata(
            resolved_at=date(2026, 1, 1),
            method=ResolutionMethod.MANUAL_SEED,
            confidence=1.0,
        )
        assert meta.confidence == 1.0

    def test_confidence_below_zero_rejected(self):
        from ai_washer.entity.types import ResolutionMetadata, ResolutionMethod

        with pytest.raises(ValidationError, match="confidence"):
            ResolutionMetadata(
                resolved_at=date(2026, 1, 1),
                method=ResolutionMethod.AUTOMATED_FUZZY,
                confidence=-0.1,
            )

    def test_confidence_above_one_rejected(self):
        from ai_washer.entity.types import ResolutionMetadata, ResolutionMethod

        with pytest.raises(ValidationError, match="confidence"):
            ResolutionMetadata(
                resolved_at=date(2026, 1, 1),
                method=ResolutionMethod.AUTOMATED_FUZZY,
                confidence=1.01,
            )

    def test_needs_review_defaults_false(self):
        from ai_washer.entity.types import ResolutionMetadata, ResolutionMethod

        meta = ResolutionMetadata(
            resolved_at=date(2026, 1, 1),
            method=ResolutionMethod.MANUAL_SEED,
            confidence=0.95,
        )
        assert meta.needs_review is False

    def test_invalid_method_rejected(self):
        from ai_washer.entity.types import ResolutionMetadata

        with pytest.raises(ValidationError):
            ResolutionMetadata(
                resolved_at=date(2026, 1, 1),
                method="unknown_method",
                confidence=0.9,
            )


class TestAliasesSchema:
    """Tests for AliasesSchema -- matches Company.aliases JSONB structure per D-02."""

    def test_full_aliases(self):
        from ai_washer.entity.types import AliasesSchema, ResolutionMetadata, ResolutionMethod

        aliases = AliasesSchema(
            cik="0001234567",
            patent_assignee=["Acme Corp", "ACME CORPORATION"],
            github_org="acme-corp",
            employer_names=["Acme", "Acme Corporation"],
            resolution_metadata=ResolutionMetadata(
                resolved_at=date(2026, 3, 27),
                method=ResolutionMethod.AUTOMATED_FUZZY,
                confidence=0.88,
                needs_review=True,
            ),
        )
        assert aliases.cik == "0001234567"
        assert "Acme Corp" in aliases.patent_assignee
        assert aliases.github_org == "acme-corp"
        assert len(aliases.employer_names) == 2
        assert aliases.resolution_metadata is not None
        assert aliases.resolution_metadata.needs_review is True

    def test_partial_resolution_allowed(self):
        """Per D-03: partial resolution (null fields) is valid."""
        from ai_washer.entity.types import AliasesSchema

        aliases = AliasesSchema(cik="0001234567")
        assert aliases.cik == "0001234567"
        assert aliases.patent_assignee == []
        assert aliases.github_org is None
        assert aliases.employer_names == []
        assert aliases.resolution_metadata is None

    def test_empty_aliases_valid(self):
        """Completely empty aliases is valid (newly added company, not yet resolved)."""
        from ai_washer.entity.types import AliasesSchema

        aliases = AliasesSchema()
        assert aliases.cik is None
        assert aliases.patent_assignee == []
        assert aliases.github_org is None
        assert aliases.employer_names == []
        assert aliases.resolution_metadata is None

    def test_aliases_fields_match_jsonb_structure(self):
        """Key fields match the D-02 JSONB structure: patent_assignee, github_org, employer_names."""
        from ai_washer.entity.types import AliasesSchema

        fields = set(AliasesSchema.model_fields.keys())
        assert "cik" in fields
        assert "patent_assignee" in fields
        assert "github_org" in fields
        assert "employer_names" in fields
        assert "resolution_metadata" in fields

    def test_serialization_roundtrip(self):
        """Aliases can be serialized to dict (for JSONB) and back."""
        from ai_washer.entity.types import AliasesSchema

        aliases = AliasesSchema(
            cik="999",
            patent_assignee=["Corp A"],
            github_org="corp-a",
            employer_names=["Corp A Inc"],
        )
        data = aliases.model_dump()
        restored = AliasesSchema.model_validate(data)
        assert restored == aliases


class TestEntityResolutionResult:
    """Tests for EntityResolutionResult Pydantic model."""

    def test_valid_result(self):
        from ai_washer.entity.types import AliasesSchema, EntityResolutionResult

        result = EntityResolutionResult(
            sec_name="ACME CORPORATION",
            matched_cik="0001234567",
            ticker="ACME",
            resolved_aliases=AliasesSchema(cik="0001234567"),
        )
        assert result.sec_name == "ACME CORPORATION"
        assert result.matched_cik == "0001234567"
        assert result.ticker == "ACME"
        assert result.resolved_aliases.cik == "0001234567"

    def test_ticker_optional(self):
        from ai_washer.entity.types import AliasesSchema, EntityResolutionResult

        result = EntityResolutionResult(
            sec_name="UNKNOWN CO",
            matched_cik="000999",
            resolved_aliases=AliasesSchema(),
        )
        assert result.ticker is None

    def test_missing_required_fields_rejected(self):
        from ai_washer.entity.types import EntityResolutionResult

        with pytest.raises(ValidationError):
            EntityResolutionResult(sec_name="Test")  # missing matched_cik and resolved_aliases
