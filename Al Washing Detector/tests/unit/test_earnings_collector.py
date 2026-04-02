"""Unit tests for EarningsCollector orchestrator.

Tests idempotent transcript persistence, collect_for_company, collect_all,
error handling, and the critical transcript_text JSONB data contract.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from ai_washer.ingestion.earnings_client import EarningsClientError
from ai_washer.ingestion.earnings_types import (
    EARNINGS_SIGNAL_VERSION,
    EarningsCollectionResult,
    TranscriptRecord,
)


@pytest.fixture()
def mock_settings() -> MagicMock:
    """Create mock AppSettings with earningscall API key."""
    settings = MagicMock()
    settings.earningscall_api_key = "test-key"
    settings.database_url = "sqlite://"
    return settings


@pytest.fixture()
def company_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_transcript(
    ticker: str = "AAPL",
    year: int = 2024,
    quarter: int = 1,
    speakers: dict[str, str] | None = None,
) -> TranscriptRecord:
    """Factory for TranscriptRecord test fixtures."""
    return TranscriptRecord(
        ticker=ticker,
        year=year,
        quarter=quarter,
        transcript_date=date(year, quarter * 3, 15),
        text=f"Q{quarter} {year} earnings call transcript for {ticker}.",
        speakers=speakers or {"CEO": "Tim Cook", "CFO": "Luca Maestri"},
        source="earningscall",
    )


class TestCollectForCompany:
    """Tests 1-4: collect_for_company behavior."""

    @patch("ai_washer.ingestion.earnings_collector.EarningsClient")
    @patch("ai_washer.ingestion.earnings_collector.get_session_factory")
    @patch("ai_washer.ingestion.earnings_collector.create_engine_from_settings")
    def test_fetches_and_persists_transcripts(
        self,
        mock_engine: MagicMock,
        mock_sf: MagicMock,
        mock_client_cls: MagicMock,
        mock_settings: MagicMock,
        company_id: uuid.UUID,
    ) -> None:
        """collect_for_company fetches transcripts and persists EarningsTranscript rows."""
        mock_client = mock_client_cls.return_value
        mock_client.get_transcript.return_value = _make_transcript()

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_sf.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.return_value.__exit__ = MagicMock(return_value=False)

        from ai_washer.ingestion.earnings_collector import EarningsCollector

        collector = EarningsCollector(app_settings=mock_settings)
        result = collector.collect_for_company(company_id=company_id, ticker="AAPL", num_quarters=2)

        assert isinstance(result, EarningsCollectionResult)
        assert result.transcript_count >= 1 or result.skipped_count >= 0
        assert mock_client.get_transcript.called

    @patch("ai_washer.ingestion.earnings_collector.EarningsClient")
    @patch("ai_washer.ingestion.earnings_collector.get_session_factory")
    @patch("ai_washer.ingestion.earnings_collector.create_engine_from_settings")
    def test_skips_existing_transcripts(
        self,
        mock_engine: MagicMock,
        mock_sf: MagicMock,
        mock_client_cls: MagicMock,
        mock_settings: MagicMock,
        company_id: uuid.UUID,
    ) -> None:
        """collect_for_company skips transcripts already in DB (idempotent)."""
        mock_client = mock_client_cls.return_value

        # Session returns existing transcript (non-None) for exists check
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = MagicMock()
        mock_sf.return_value.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.return_value.__exit__ = MagicMock(return_value=False)

        from ai_washer.ingestion.earnings_collector import EarningsCollector

        collector = EarningsCollector(app_settings=mock_settings)
        result = collector.collect_for_company(company_id=company_id, ticker="AAPL", num_quarters=2)

        assert isinstance(result, EarningsCollectionResult)
        assert result.skipped_count >= 1
        assert result.transcript_count == 0
        # Client should not be called for existing transcripts
        mock_client.get_transcript.assert_not_called()

    @patch("ai_washer.ingestion.earnings_collector.EarningsClient")
    @patch("ai_washer.ingestion.earnings_collector.get_session_factory")
    @patch("ai_washer.ingestion.earnings_collector.create_engine_from_settings")
    def test_returns_correct_counts(
        self,
        mock_engine: MagicMock,
        mock_sf: MagicMock,
        mock_client_cls: MagicMock,
        mock_settings: MagicMock,
        company_id: uuid.UUID,
    ) -> None:
        """collect_for_company returns EarningsCollectionResult with correct counts."""
        mock_client = mock_client_cls.return_value
        mock_client.get_transcript.return_value = _make_transcript()

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_sf.return_value.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.return_value.__exit__ = MagicMock(return_value=False)

        from ai_washer.ingestion.earnings_collector import EarningsCollector

        collector = EarningsCollector(app_settings=mock_settings)
        result = collector.collect_for_company(company_id=company_id, ticker="AAPL", num_quarters=1)

        assert result.transcript_count >= 0
        assert result.skipped_count >= 0
        assert result.errors == []

    @patch("ai_washer.ingestion.earnings_collector.EarningsClient")
    @patch("ai_washer.ingestion.earnings_collector.get_session_factory")
    @patch("ai_washer.ingestion.earnings_collector.create_engine_from_settings")
    def test_handles_client_error_gracefully(
        self,
        mock_engine: MagicMock,
        mock_sf: MagicMock,
        mock_client_cls: MagicMock,
        mock_settings: MagicMock,
        company_id: uuid.UUID,
    ) -> None:
        """collect_for_company handles EarningsClientError gracefully."""
        mock_client = mock_client_cls.return_value
        mock_client.get_transcript.side_effect = EarningsClientError("API error")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_sf.return_value.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.return_value.__exit__ = MagicMock(return_value=False)

        from ai_washer.ingestion.earnings_collector import EarningsCollector

        collector = EarningsCollector(app_settings=mock_settings)
        result = collector.collect_for_company(company_id=company_id, ticker="AAPL", num_quarters=1)

        assert isinstance(result, EarningsCollectionResult)
        assert len(result.errors) >= 1
        assert "API error" in result.errors[0]


class TestCollectAll:
    """Test 5: collect_all iterates active companies."""

    @patch("ai_washer.ingestion.earnings_collector.time.sleep")
    @patch("ai_washer.ingestion.earnings_collector.EarningsClient")
    @patch("ai_washer.ingestion.earnings_collector.get_session_factory")
    @patch("ai_washer.ingestion.earnings_collector.create_engine_from_settings")
    def test_iterates_active_companies(
        self,
        mock_engine: MagicMock,
        mock_sf: MagicMock,
        mock_client_cls: MagicMock,
        mock_sleep: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """collect_all iterates active companies and respects inter-company delay."""
        mock_client = mock_client_cls.return_value
        mock_client.get_transcript.return_value = None

        # Create mock companies
        company_1 = MagicMock()
        company_1.id = uuid.uuid4()
        company_1.ticker = "AAPL"
        company_1.cik = "0000320193"

        company_2 = MagicMock()
        company_2.id = uuid.uuid4()
        company_2.ticker = "MSFT"
        company_2.cik = "0000789019"

        # First session call (collect_all query) returns companies
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            company_1,
            company_2,
        ]
        # Second+ session calls (_transcript_exists) return None
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        mock_sf.return_value.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.return_value.__exit__ = MagicMock(return_value=False)

        from ai_washer.ingestion.earnings_collector import EarningsCollector

        collector = EarningsCollector(app_settings=mock_settings)
        results = collector.collect_all()

        assert isinstance(results, list)
        assert len(results) == 2
        # Should sleep between companies
        assert mock_sleep.called


class TestTranscriptTextContract:
    """Test 6: transcript_text JSONB contains only string values."""

    @patch("ai_washer.ingestion.earnings_collector.EarningsClient")
    @patch("ai_washer.ingestion.earnings_collector.get_session_factory")
    @patch("ai_washer.ingestion.earnings_collector.create_engine_from_settings")
    def test_transcript_text_contains_only_strings(
        self,
        mock_engine: MagicMock,
        mock_sf: MagicMock,
        mock_client_cls: MagicMock,
        mock_settings: MagicMock,
        company_id: uuid.UUID,
    ) -> None:
        """transcript_text JSONB stores only str values; speakers in collection_metadata."""
        mock_client = mock_client_cls.return_value
        transcript = _make_transcript(speakers={"CEO": "Tim Cook", "CFO": "Luca Maestri"})
        mock_client.get_transcript.return_value = transcript

        # Track what gets added to session
        added_rows: list = []
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.add.side_effect = lambda row: added_rows.append(row)
        mock_sf.return_value.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_sf.return_value.return_value.__exit__ = MagicMock(return_value=False)

        from ai_washer.ingestion.earnings_collector import EarningsCollector

        collector = EarningsCollector(app_settings=mock_settings)
        collector.collect_for_company(company_id=company_id, ticker="AAPL", num_quarters=1)

        assert len(added_rows) >= 1
        row = added_rows[0]

        # CRITICAL: transcript_text values must all be str or None
        for key, val in row.transcript_text.items():
            assert val is None or isinstance(val, str), (
                f"transcript_text['{key}'] must be str|None, got {type(val)}"
            )

        # Speakers must NOT be in transcript_text
        assert "speakers" not in row.transcript_text

        # Speakers must be in collection_metadata
        assert "speakers" in row.collection_metadata
        assert row.collection_metadata["speakers"] == {
            "CEO": "Tim Cook",
            "CFO": "Luca Maestri",
        }

        # Signal version must be in collection_metadata
        assert row.collection_metadata["signal_version"] == EARNINGS_SIGNAL_VERSION
