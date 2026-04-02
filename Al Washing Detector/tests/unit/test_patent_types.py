"""Unit tests for patent type contracts.

Tests PatentRecord validation, PatentForScoring immutability, PatentCollectionResult
defaults, and CPC_AI_PREFIXES / PATENT_SIGNAL_VERSION constants.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest
from pydantic import ValidationError

from ai_washer.ingestion.patent_types import (
    CPC_AI_PREFIXES,
    PATENT_SIGNAL_VERSION,
    PatentCollectionResult,
    PatentForScoring,
    PatentRecord,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify module-level constants."""

    def test_cpc_ai_prefixes_is_tuple(self) -> None:
        assert isinstance(CPC_AI_PREFIXES, tuple)

    def test_cpc_ai_prefixes_contains_g06n(self) -> None:
        assert "G06N" in CPC_AI_PREFIXES

    def test_cpc_ai_prefixes_contains_g06f18(self) -> None:
        assert "G06F18" in CPC_AI_PREFIXES

    def test_patent_signal_version(self) -> None:
        assert PATENT_SIGNAL_VERSION == "0.5.0"


# ---------------------------------------------------------------------------
# PatentRecord
# ---------------------------------------------------------------------------


class TestPatentRecord:
    """Validate PatentRecord Pydantic schema."""

    def test_valid_patent_record(self) -> None:
        record = PatentRecord(
            patent_id="US-12345678-A1",
            patent_title="Neural network training method",
            patent_date=date(2025, 6, 15),
            assignee_organization="Acme Corp",
            cpc_codes=["G06N3/08", "G06F18/24"],
        )
        assert record.patent_id == "US-12345678-A1"
        assert record.patent_title == "Neural network training method"
        assert record.patent_date == date(2025, 6, 15)
        assert record.assignee_organization == "Acme Corp"
        assert record.cpc_codes == ["G06N3/08", "G06F18/24"]

    def test_patent_record_default_cpc_codes(self) -> None:
        record = PatentRecord(
            patent_id="US-99999999-B2",
            patent_title="A method",
            patent_date=date(2024, 1, 1),
            assignee_organization="Test Inc",
        )
        assert record.cpc_codes == []

    def test_patent_record_rejects_empty_patent_id(self) -> None:
        with pytest.raises(ValidationError):
            PatentRecord(
                patent_id="",
                patent_title="Some title",
                patent_date=date(2024, 1, 1),
                assignee_organization="Test",
            )

    def test_patent_record_rejects_empty_patent_title(self) -> None:
        with pytest.raises(ValidationError):
            PatentRecord(
                patent_id="US-12345678-A1",
                patent_title="",
                patent_date=date(2024, 1, 1),
                assignee_organization="Test",
            )


# ---------------------------------------------------------------------------
# PatentForScoring
# ---------------------------------------------------------------------------


class TestPatentForScoring:
    """Validate PatentForScoring frozen dataclass."""

    def test_create_patent_for_scoring(self) -> None:
        p = PatentForScoring(
            patent_id="US-12345678-A1",
            grant_date=date(2025, 6, 15),
            cpc_codes=("G06N3/08", "G06F18/24"),
            assignee_organization="Acme Corp",
        )
        assert p.patent_id == "US-12345678-A1"
        assert p.grant_date == date(2025, 6, 15)
        assert p.cpc_codes == ("G06N3/08", "G06F18/24")
        assert p.assignee_organization == "Acme Corp"

    def test_patent_for_scoring_is_frozen(self) -> None:
        p = PatentForScoring(
            patent_id="US-12345678-A1",
            grant_date=date(2025, 6, 15),
            cpc_codes=("G06N3/08",),
            assignee_organization="Acme Corp",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.patent_id = "changed"  # type: ignore[misc]

    def test_patent_for_scoring_cpc_codes_is_tuple(self) -> None:
        p = PatentForScoring(
            patent_id="US-12345678-A1",
            grant_date=date(2025, 6, 15),
            cpc_codes=("G06N3/08",),
            assignee_organization="Acme Corp",
        )
        assert isinstance(p.cpc_codes, tuple)


# ---------------------------------------------------------------------------
# PatentCollectionResult
# ---------------------------------------------------------------------------


class TestPatentCollectionResult:
    """Validate PatentCollectionResult defaults and fields."""

    def test_defaults(self) -> None:
        result = PatentCollectionResult(company_cik="0001234567")
        assert result.company_cik == "0001234567"
        assert result.patent_count == 0
        assert result.skipped_count == 0
        assert result.errors == []

    def test_custom_values(self) -> None:
        result = PatentCollectionResult(
            company_cik="0001234567",
            patent_count=5,
            skipped_count=2,
            errors=["Rate limited"],
        )
        assert result.patent_count == 5
        assert result.skipped_count == 2
        assert result.errors == ["Rate limited"]

    def test_errors_list_isolation(self) -> None:
        """Verify default_factory creates independent lists."""
        r1 = PatentCollectionResult(company_cik="001")
        r2 = PatentCollectionResult(company_cik="002")
        assert r1.errors is not r2.errors
