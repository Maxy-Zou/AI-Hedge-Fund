"""Unit tests for EarningsClient API wrapper.

Tests lazy API key validation, transcript retrieval, quarter enumeration,
and error handling -- all with mocked earningscall library.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from ai_washer.ingestion.earnings_client import EarningsClient, EarningsClientError
from ai_washer.ingestion.earnings_types import TranscriptRecord


class TestEarningsClientLazyValidation:
    """Test 1: Lazy API key validation."""

    def test_empty_key_constructs_without_error(self) -> None:
        """EarningsClient(api_key='') constructs without error."""
        client = EarningsClient(api_key="")
        assert client is not None

    def test_empty_key_raises_on_get_transcript(self) -> None:
        """EarningsClient(api_key='').get_transcript raises EarningsClientError."""
        client = EarningsClient(api_key="")
        with pytest.raises(EarningsClientError, match="API key required"):
            client.get_transcript("AAPL", 2024, 1)


class TestGetTranscript:
    """Tests 3-4: Transcript retrieval with mocked earningscall."""

    @patch("ai_washer.ingestion.earnings_client.earningscall")
    def test_returns_transcript_record_on_success(self, mock_ec: MagicMock) -> None:
        """get_transcript returns TranscriptRecord when earningscall returns data."""
        # Build mock transcript
        mock_transcript = MagicMock()
        mock_transcript.text = "Q1 2024 earnings call full text"
        mock_transcript.prepared_remarks = "Prepared remarks here"
        mock_transcript.questions_and_answers = "Q&A section"
        mock_speaker_info = MagicMock()
        mock_speaker_info.name = "Tim Cook"
        mock_speaker_info.title = "CEO"
        mock_speaker = MagicMock()
        mock_speaker.speaker_info = mock_speaker_info
        mock_speaker.text = "Some text"
        mock_transcript.speakers = [mock_speaker]
        mock_transcript.event = MagicMock(conference_date=date(2024, 1, 25))

        mock_company = MagicMock()
        mock_company.get_transcript.return_value = mock_transcript
        mock_ec.get_company.return_value = mock_company

        client = EarningsClient(api_key="test-key")
        result = client.get_transcript("AAPL", 2024, 1)

        assert result is not None
        assert isinstance(result, TranscriptRecord)
        assert result.ticker == "AAPL"
        assert result.year == 2024
        assert result.quarter == 1
        assert result.text == "Q1 2024 earnings call full text"
        assert result.transcript_date == date(2024, 1, 25)
        assert result.source == "earningscall"
        mock_ec.get_company.assert_called_once_with("AAPL")
        mock_company.get_transcript.assert_called_once_with(year=2024, quarter=1)

    @patch("ai_washer.ingestion.earnings_client.earningscall")
    def test_returns_none_when_transcript_is_none(self, mock_ec: MagicMock) -> None:
        """get_transcript returns None when earningscall returns None."""
        mock_company = MagicMock()
        mock_company.get_transcript.return_value = None
        mock_ec.get_company.return_value = mock_company

        client = EarningsClient(api_key="test-key")
        result = client.get_transcript("AAPL", 2024, 1)

        assert result is None


class TestGetQuartersAvailable:
    """Test 5: Quarter enumeration."""

    @patch("ai_washer.ingestion.earnings_client.earningscall")
    def test_returns_year_quarter_tuples(self, mock_ec: MagicMock) -> None:
        """get_quarters_available returns list of (year, quarter) tuples."""
        mock_event_1 = MagicMock()
        mock_event_1.year = 2024
        mock_event_1.quarter = 1
        mock_event_1.conference_date = date(2024, 1, 25)

        mock_event_2 = MagicMock()
        mock_event_2.year = 2023
        mock_event_2.quarter = 4
        mock_event_2.conference_date = date(2023, 10, 26)

        mock_company = MagicMock()
        mock_company.events.return_value = [mock_event_1, mock_event_2]
        mock_ec.get_company.return_value = mock_company

        client = EarningsClient(api_key="test-key")
        result = client.get_quarters_available("AAPL")

        assert isinstance(result, list)
        assert len(result) == 2
        assert (2024, 1) in result
        assert (2023, 4) in result


class TestErrorHandling:
    """Test 6: Graceful exception wrapping."""

    @patch("ai_washer.ingestion.earnings_client.earningscall")
    def test_wraps_earningscall_exception_in_client_error(self, mock_ec: MagicMock) -> None:
        """EarningsClient wraps earningscall exceptions in EarningsClientError."""
        mock_ec.get_company.side_effect = RuntimeError("API connection failed")

        client = EarningsClient(api_key="test-key")
        with pytest.raises(EarningsClientError, match="API connection failed"):
            client.get_transcript("AAPL", 2024, 1)
