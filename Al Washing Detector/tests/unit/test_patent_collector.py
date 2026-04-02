"""Unit tests for PatentCollector.

Tests cover assignee alias expansion, incremental collection logic,
deduplication across assignee name searches, error handling,
and collection metadata fields. All tests use mocked PatentSearchClient
and mock database sessions (no real DB or API calls).
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, call, patch

import pytest

from ai_washer.ingestion.patent_client import PatentClientError
from ai_washer.ingestion.patent_collector import PatentCollector
from ai_washer.ingestion.patent_types import (
    PATENT_SIGNAL_VERSION,
    PatentRecord,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_ID = uuid.uuid4()
COMPANY_CIK = "0001234567"
COMPANY_NAME = "Acme Corp"


def _make_patent_record(
    patent_id: str = "US-11234567-B2",
    title: str = "Neural network method",
    patent_date: date = date(2025, 6, 15),
    assignee: str = "Acme Corp",
    cpc_codes: list[str] | None = None,
) -> PatentRecord:
    return PatentRecord(
        patent_id=patent_id,
        patent_title=title,
        patent_date=patent_date,
        assignee_organization=assignee,
        cpc_codes=cpc_codes or ["G06N3/08"],
    )


@pytest.fixture()
def mock_patent_client():
    """Create a mocked PatentSearchClient."""
    with patch(
        "ai_washer.ingestion.patent_collector.PatentSearchClient"
    ) as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def mock_session_factory():
    """Create a mocked session factory returning a mock session."""
    mock_session = MagicMock()
    # Default: no existing patents (first collection)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    mock_factory = MagicMock(return_value=mock_session)
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_factory


@pytest.fixture()
def collector(mock_patent_client, mock_session_factory):
    """Create a PatentCollector with mocked dependencies."""
    with patch(
        "ai_washer.ingestion.patent_collector.create_engine_from_settings"
    ), patch(
        "ai_washer.ingestion.patent_collector.get_session_factory",
        return_value=mock_session_factory,
    ), patch(
        "ai_washer.ingestion.patent_collector.PatentSearchClient"
    ) as mock_cls:
        mock_cls.return_value = mock_patent_client
        c = PatentCollector.__new__(PatentCollector)
        c._log = MagicMock()
        c._patent_client = mock_patent_client
        c._session_factory = mock_session_factory
        return c


# ---------------------------------------------------------------------------
# Tests: Assignee alias expansion
# ---------------------------------------------------------------------------


class TestAssigneeAliases:
    """Tests for assignee name extraction and alias expansion."""

    def test_collect_uses_assignee_aliases(
        self, collector, mock_patent_client, mock_session_factory
    ) -> None:
        """Verify all aliases are searched."""
        aliases = {"patent_assignee": ["Acme Corp", "ACME CORPORATION", "Acme Inc"]}

        mock_patent_client.search_by_assignee.return_value = []

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            aliases=aliases,
        )

        # Should search for each alias
        assert mock_patent_client.search_by_assignee.call_count == 3
        searched_names = [
            c.args[0] for c in mock_patent_client.search_by_assignee.call_args_list
        ]
        assert "Acme Corp" in searched_names
        assert "ACME CORPORATION" in searched_names
        assert "Acme Inc" in searched_names

    def test_collect_falls_back_to_company_name(
        self, collector, mock_patent_client, mock_session_factory
    ) -> None:
        """When aliases empty, uses company name."""
        aliases = {"patent_assignee": []}

        mock_patent_client.search_by_assignee.return_value = []

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            aliases=aliases,
        )

        assert mock_patent_client.search_by_assignee.call_count == 1
        assert mock_patent_client.search_by_assignee.call_args.args[0] == COMPANY_NAME

    def test_collect_falls_back_when_no_patent_assignee_key(
        self, collector, mock_patent_client, mock_session_factory
    ) -> None:
        """When aliases dict has no patent_assignee key, falls back to name."""
        aliases = {"github_org": "acme"}

        mock_patent_client.search_by_assignee.return_value = []

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            aliases=aliases,
        )

        assert mock_patent_client.search_by_assignee.call_count == 1
        assert mock_patent_client.search_by_assignee.call_args.args[0] == COMPANY_NAME


# ---------------------------------------------------------------------------
# Tests: Incremental collection
# ---------------------------------------------------------------------------


class TestIncrementalCollection:
    """Tests for incremental collection via last_patent_date."""

    def test_incremental_uses_last_date(
        self, collector, mock_patent_client, mock_session_factory
    ) -> None:
        """Verify after_date passed when existing patents exist."""
        mock_session = mock_session_factory.return_value.__enter__.return_value

        # First call: return last patent date for _get_last_patent_date
        mock_date_result = MagicMock()
        mock_date_result.scalar_one_or_none.return_value = date(2025, 3, 1)

        # Subsequent calls: return None for _patent_exists checks
        mock_exists_result = MagicMock()
        mock_exists_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [mock_date_result, mock_exists_result]

        mock_patent_client.search_by_assignee.return_value = [
            _make_patent_record()
        ]

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            aliases={},
        )

        # Verify after_date was passed to search_by_assignee
        call_kwargs = mock_patent_client.search_by_assignee.call_args
        assert call_kwargs.kwargs.get("after_date") == date(2025, 3, 1)

    def test_first_collection_no_date_filter(
        self, collector, mock_patent_client, mock_session_factory
    ) -> None:
        """Verify after_date is None for new company (no existing patents)."""
        mock_session = mock_session_factory.return_value.__enter__.return_value

        # Return None for _get_last_patent_date (no existing patents)
        mock_date_result = MagicMock()
        mock_date_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_date_result

        mock_patent_client.search_by_assignee.return_value = []

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            aliases={},
        )

        call_kwargs = mock_patent_client.search_by_assignee.call_args
        assert call_kwargs.kwargs.get("after_date") is None


# ---------------------------------------------------------------------------
# Tests: Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Tests for cross-assignee deduplication."""

    def test_deduplicates_across_searches(
        self, collector, mock_patent_client, mock_session_factory
    ) -> None:
        """Same patent_id from two assignee names counted once."""
        mock_session = mock_session_factory.return_value.__enter__.return_value

        # Setup: _get_last_patent_date returns None (first collection)
        mock_date_result = MagicMock()
        mock_date_result.scalar_one_or_none.return_value = None

        # Setup: _patent_exists returns None (patent not in DB)
        mock_exists_result = MagicMock()
        mock_exists_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [
            mock_date_result,  # _get_last_patent_date
            mock_exists_result,  # _patent_exists for the 1 unique patent
        ]

        # Same patent returned by two different assignee name searches
        same_patent = _make_patent_record(patent_id="US-11234567-B2")
        aliases = {"patent_assignee": ["Acme Corp", "ACME CORPORATION"]}

        mock_patent_client.search_by_assignee.return_value = [same_patent]

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            aliases=aliases,
        )

        # Should count only 1 patent (deduplicated), not 2
        assert result.patent_count == 1


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for graceful error handling."""

    def test_client_error_caught_and_logged(
        self, collector, mock_patent_client, mock_session_factory
    ) -> None:
        """PatentClientError produces error in result, not exception."""
        mock_session = mock_session_factory.return_value.__enter__.return_value

        mock_date_result = MagicMock()
        mock_date_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_date_result

        mock_patent_client.search_by_assignee.side_effect = PatentClientError(
            "API key missing"
        )

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            aliases={},
        )

        # Should not raise, but result should contain error
        assert len(result.errors) >= 1
        assert "API key missing" in result.errors[0]
        assert result.patent_count == 0


# ---------------------------------------------------------------------------
# Tests: Collection metadata
# ---------------------------------------------------------------------------


class TestCollectionMetadata:
    """Tests for collection metadata fields."""

    def test_collection_metadata_fields(
        self, collector, mock_patent_client, mock_session_factory
    ) -> None:
        """Verify signal_version and assignee_names_searched in metadata."""
        mock_session = mock_session_factory.return_value.__enter__.return_value

        mock_date_result = MagicMock()
        mock_date_result.scalar_one_or_none.return_value = None

        mock_exists_result = MagicMock()
        mock_exists_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [mock_date_result, mock_exists_result]

        mock_patent_client.search_by_assignee.return_value = [
            _make_patent_record()
        ]

        aliases = {"patent_assignee": ["Acme Corp"]}

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            aliases=aliases,
        )

        # Check that session.add was called with a Patent model row
        add_calls = mock_session.add.call_args_list
        assert len(add_calls) >= 1

        patent_row = add_calls[0].args[0]
        metadata = patent_row.collection_metadata
        assert metadata["signal_version"] == PATENT_SIGNAL_VERSION
        assert "Acme Corp" in metadata["assignee_names_searched"]
        assert "api_query_count" in metadata
