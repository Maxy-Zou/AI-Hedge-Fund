"""Unit tests for earnings transcript Pydantic type contracts."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from ai_washer.ingestion.earnings_types import (
    EARNINGS_SIGNAL_VERSION,
    EarningsCollectionResult,
    TranscriptRecord,
)


class TestTranscriptRecord:
    """Tests for TranscriptRecord Pydantic model."""

    def test_valid_transcript_record(self) -> None:
        """TranscriptRecord validates with ticker, year, quarter, text fields."""
        record = TranscriptRecord(
            ticker="AAPL",
            year=2025,
            quarter=1,
            text="We are investing heavily in AI infrastructure.",
        )
        assert record.ticker == "AAPL"
        assert record.year == 2025
        assert record.quarter == 1
        assert record.text == "We are investing heavily in AI infrastructure."
        assert record.transcript_date is None
        assert record.speakers is None
        assert record.source == "earningscall"

    def test_rejects_quarter_zero(self) -> None:
        """TranscriptRecord rejects quarter=0 with ValidationError."""
        with pytest.raises(ValidationError, match="quarter"):
            TranscriptRecord(ticker="AAPL", year=2025, quarter=0, text="text")

    def test_rejects_quarter_five(self) -> None:
        """TranscriptRecord rejects quarter=5 with ValidationError."""
        with pytest.raises(ValidationError, match="quarter"):
            TranscriptRecord(ticker="AAPL", year=2025, quarter=5, text="text")

    def test_with_speakers_dict(self) -> None:
        """TranscriptRecord with speakers dict serializes correctly."""
        speakers = {"CEO": "Tim Cook", "CFO": "Luca Maestri"}
        record = TranscriptRecord(
            ticker="AAPL",
            year=2025,
            quarter=2,
            text="AI is our future.",
            speakers=speakers,
        )
        assert record.speakers == speakers
        dumped = record.model_dump()
        assert dumped["speakers"] == speakers

    def test_with_transcript_date(self) -> None:
        """TranscriptRecord accepts an optional transcript_date."""
        record = TranscriptRecord(
            ticker="MSFT",
            year=2024,
            quarter=4,
            text="We deployed copilot across all products.",
            transcript_date=date(2024, 10, 25),
        )
        assert record.transcript_date == date(2024, 10, 25)


class TestEarningsCollectionResult:
    """Tests for EarningsCollectionResult frozen Pydantic model."""

    def test_immutable_collection_result(self) -> None:
        """EarningsCollectionResult is immutable (frozen=True pattern)."""
        result = EarningsCollectionResult(
            company_cik="0001234567",
            transcript_count=4,
            skipped_count=1,
            errors=["Q3 not found"],
        )
        assert result.company_cik == "0001234567"
        assert result.transcript_count == 4
        assert result.skipped_count == 1
        assert result.errors == ["Q3 not found"]

        with pytest.raises(ValidationError):
            result.transcript_count = 10  # type: ignore[misc]

    def test_default_values(self) -> None:
        """EarningsCollectionResult has sensible defaults."""
        result = EarningsCollectionResult(company_cik="0001234567")
        assert result.transcript_count == 0
        assert result.skipped_count == 0
        assert result.errors == []


class TestConstants:
    """Tests for module-level constants."""

    def test_signal_version(self) -> None:
        """EARNINGS_SIGNAL_VERSION equals '0.7.0'."""
        assert EARNINGS_SIGNAL_VERSION == "0.7.0"
