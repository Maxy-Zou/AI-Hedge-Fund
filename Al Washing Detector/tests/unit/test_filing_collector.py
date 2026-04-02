"""Unit tests for FilingCollector orchestrator.

Tests cover filing retrieval, XBRL extraction, database persistence
with dual timestamps, idempotent skip logic, error handling, and
collect_all iteration with rate limiting.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from ai_washer.ingestion.types import (
    CollectionResult,
    FilingData,
    FilingSections,
    XBRLFactRecord,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_filing_data(
    accession_no: str = "0001234567-26-000001",
    form_type: str = "10-K",
    filing_date: date = date(2026, 1, 15),
    period_of_report: date | None = date(2025, 12, 31),
) -> FilingData:
    """Build a FilingData fixture."""
    return FilingData(
        accession_no=accession_no,
        form_type=form_type,
        filing_date=filing_date,
        period_of_report=period_of_report,
        sections=FilingSections(
            business="Business description " * 100,
            risk_factors="Risk factors text " * 100,
            mda="Management discussion " * 100,
        ),
        content_hash="abc123hash",
        entity_name="Test Corp",
    )


def _make_xbrl_fact(
    concept: str = "rd_expense",
    tag: str = "ResearchAndDevelopmentExpense",
    end_date: date = date(2025, 12, 31),
    value_cents: int = 500_000_000_00,
    fiscal_year: int = 2025,
    fiscal_period: str = "FY",
    accession_no: str = "0001234567-26-000001",
) -> XBRLFactRecord:
    """Build an XBRLFactRecord fixture."""
    return XBRLFactRecord(
        tag=tag,
        concept=concept,
        end_date=end_date,
        value_cents=value_cents,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form_type="10-K",
        filed_date=date(2026, 1, 15),
        accession_no=accession_no,
    )


def _make_company_mock(
    company_id: uuid.UUID | None = None,
    ticker: str = "TEST",
    cik: str = "1234567",
    is_active: bool = True,
) -> MagicMock:
    """Build a mock Company object."""
    company = MagicMock()
    company.id = company_id or uuid.uuid4()
    company.ticker = ticker
    company.cik = cik
    company.is_active = is_active
    return company


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestFilingCollectorForCompany:
    """Tests for collect_for_company method."""

    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_inserts_filing_rows_with_dual_timestamps(
        self, mock_engine, mock_sf, mock_filing_cls, mock_xbrl_cls
    ):
        """Test 1: Filing rows have correct as_of_date and observed_date."""
        from ai_washer.ingestion.filing_collector import FilingCollector

        mock_engine.return_value = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_session)

        filing = _make_filing_data(period_of_report=date(2025, 12, 31))
        mock_client = MagicMock()
        mock_client.get_latest_filings.return_value = [filing]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_filing_cls.return_value = mock_client

        mock_xbrl = MagicMock()
        mock_xbrl.extract_company_xbrl.return_value = []
        mock_xbrl.__enter__ = MagicMock(return_value=mock_xbrl)
        mock_xbrl.__exit__ = MagicMock(return_value=False)
        mock_xbrl_cls.return_value = mock_xbrl

        app_settings = MagicMock()
        app_settings.edgar_identity = "Test test@test.com"
        collector = FilingCollector(app_settings=app_settings)

        company_id = uuid.uuid4()
        collection_date = date(2026, 3, 27)
        result = collector.collect_for_company(
            company_id=company_id,
            cik="1234567",
            ticker="TEST",
            collection_date=collection_date,
        )

        # Verify session.add was called with Filing objects
        add_calls = mock_session.add.call_args_list
        assert len(add_calls) >= 1

        # Check the Filing object passed to session.add
        filing_obj = add_calls[0][0][0]
        assert filing_obj.as_of_date == date(2025, 12, 31)
        assert filing_obj.observed_date == collection_date
        assert filing_obj.company_id == company_id

    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_inserts_xbrl_facts_with_dual_timestamps(
        self, mock_engine, mock_sf, mock_filing_cls, mock_xbrl_cls
    ):
        """Test 2: XBRLFact rows have correct as_of_date and observed_date."""
        from ai_washer.ingestion.filing_collector import FilingCollector

        mock_engine.return_value = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_session)

        mock_client = MagicMock()
        mock_client.get_latest_filings.return_value = []
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_filing_cls.return_value = mock_client

        xbrl_fact = _make_xbrl_fact(end_date=date(2025, 12, 31))
        mock_xbrl = MagicMock()
        mock_xbrl.extract_company_xbrl.return_value = [xbrl_fact]
        mock_xbrl.__enter__ = MagicMock(return_value=mock_xbrl)
        mock_xbrl.__exit__ = MagicMock(return_value=False)
        mock_xbrl_cls.return_value = mock_xbrl

        app_settings = MagicMock()
        app_settings.edgar_identity = "Test test@test.com"
        collector = FilingCollector(app_settings=app_settings)

        company_id = uuid.uuid4()
        collection_date = date(2026, 3, 27)
        result = collector.collect_for_company(
            company_id=company_id,
            cik="1234567",
            ticker="TEST",
            collection_date=collection_date,
        )

        assert result.xbrl_fact_count == 1

        # Find the XBRLFact object in session.add calls
        xbrl_adds = [
            c[0][0]
            for c in mock_session.add.call_args_list
            if hasattr(c[0][0], "concept")
        ]
        assert len(xbrl_adds) == 1
        xbrl_obj = xbrl_adds[0]
        assert xbrl_obj.as_of_date == date(2025, 12, 31)
        assert xbrl_obj.observed_date == collection_date

    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_idempotency_skips_existing_filing(
        self, mock_engine, mock_sf, mock_filing_cls, mock_xbrl_cls
    ):
        """Test 3: Skips filing when same (company_id, form_type, accession_no) exists."""
        from ai_washer.ingestion.filing_collector import FilingCollector

        mock_engine.return_value = MagicMock()
        mock_session = MagicMock()
        # Return an existing filing on query
        mock_session.execute.return_value.scalar_one_or_none.return_value = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_session)

        filing = _make_filing_data()
        mock_client = MagicMock()
        mock_client.get_latest_filings.return_value = [filing]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_filing_cls.return_value = mock_client

        mock_xbrl = MagicMock()
        mock_xbrl.extract_company_xbrl.return_value = []
        mock_xbrl.__enter__ = MagicMock(return_value=mock_xbrl)
        mock_xbrl.__exit__ = MagicMock(return_value=False)
        mock_xbrl_cls.return_value = mock_xbrl

        app_settings = MagicMock()
        app_settings.edgar_identity = "Test test@test.com"
        collector = FilingCollector(app_settings=app_settings)

        result = collector.collect_for_company(
            company_id=uuid.uuid4(),
            cik="1234567",
            ticker="TEST",
        )

        # Filing was skipped (already exists)
        assert result.skipped_count >= 1
        assert result.filing_count == 0

    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_idempotency_skips_existing_xbrl_fact(
        self, mock_engine, mock_sf, mock_filing_cls, mock_xbrl_cls
    ):
        """Test 4: Skips XBRLFact when same (company_id, concept, end_date, fiscal_period) exists."""
        from ai_washer.ingestion.filing_collector import FilingCollector

        mock_engine.return_value = MagicMock()
        mock_session = MagicMock()
        # First call for filing check returns None (no filing), subsequent for XBRL returns existing
        mock_session.execute.return_value.scalar_one_or_none.return_value = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_session)

        mock_client = MagicMock()
        mock_client.get_latest_filings.return_value = []
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_filing_cls.return_value = mock_client

        xbrl_fact = _make_xbrl_fact()
        mock_xbrl = MagicMock()
        mock_xbrl.extract_company_xbrl.return_value = [xbrl_fact]
        mock_xbrl.__enter__ = MagicMock(return_value=mock_xbrl)
        mock_xbrl.__exit__ = MagicMock(return_value=False)
        mock_xbrl_cls.return_value = mock_xbrl

        app_settings = MagicMock()
        app_settings.edgar_identity = "Test test@test.com"
        collector = FilingCollector(app_settings=app_settings)

        result = collector.collect_for_company(
            company_id=uuid.uuid4(),
            cik="1234567",
            ticker="TEST",
        )

        # XBRL fact was skipped
        assert result.xbrl_fact_count == 0
        assert result.skipped_count >= 1

    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_returns_correct_collection_result_counts(
        self, mock_engine, mock_sf, mock_filing_cls, mock_xbrl_cls
    ):
        """Test 5: CollectionResult has correct filing_count, xbrl_fact_count, skipped_count."""
        from ai_washer.ingestion.filing_collector import FilingCollector

        mock_engine.return_value = MagicMock()
        mock_session = MagicMock()
        # No existing records -- all inserts go through
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_session)

        filings = [
            _make_filing_data(accession_no="0001-26-001"),
            _make_filing_data(accession_no="0001-26-002"),
        ]
        mock_client = MagicMock()
        mock_client.get_latest_filings.return_value = filings
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_filing_cls.return_value = mock_client

        xbrl_facts = [
            _make_xbrl_fact(concept="rd_expense", end_date=date(2025, 12, 31)),
            _make_xbrl_fact(concept="capex", end_date=date(2025, 12, 31)),
            _make_xbrl_fact(concept="revenue", end_date=date(2025, 12, 31)),
        ]
        mock_xbrl = MagicMock()
        mock_xbrl.extract_company_xbrl.return_value = xbrl_facts
        mock_xbrl.__enter__ = MagicMock(return_value=mock_xbrl)
        mock_xbrl.__exit__ = MagicMock(return_value=False)
        mock_xbrl_cls.return_value = mock_xbrl

        app_settings = MagicMock()
        app_settings.edgar_identity = "Test test@test.com"
        collector = FilingCollector(app_settings=app_settings)

        result = collector.collect_for_company(
            company_id=uuid.uuid4(),
            cik="1234567",
            ticker="TEST",
        )

        assert isinstance(result, CollectionResult)
        assert result.company_cik == "1234567"
        # 2 filings * 3 form types = 6 total (filings returned for each form type)
        assert result.filing_count == 6
        assert result.xbrl_fact_count == 3
        assert result.skipped_count == 0

    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_catches_per_form_type_errors(
        self, mock_engine, mock_sf, mock_filing_cls, mock_xbrl_cls
    ):
        """Test 6: Per-form-type errors are caught and added to errors list."""
        from ai_washer.ingestion.filing_collector import FilingCollector

        mock_engine.return_value = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_session)

        mock_client = MagicMock()
        mock_client.get_latest_filings.side_effect = RuntimeError("SEC API down")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_filing_cls.return_value = mock_client

        mock_xbrl = MagicMock()
        mock_xbrl.extract_company_xbrl.return_value = []
        mock_xbrl.__enter__ = MagicMock(return_value=mock_xbrl)
        mock_xbrl.__exit__ = MagicMock(return_value=False)
        mock_xbrl_cls.return_value = mock_xbrl

        app_settings = MagicMock()
        app_settings.edgar_identity = "Test test@test.com"
        collector = FilingCollector(app_settings=app_settings)

        result = collector.collect_for_company(
            company_id=uuid.uuid4(),
            cik="1234567",
            ticker="TEST",
        )

        # Errors were captured, not raised
        assert len(result.errors) >= 1
        assert "SEC API down" in result.errors[0]

    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_filing_sections_stored_as_dict(
        self, mock_engine, mock_sf, mock_filing_cls, mock_xbrl_cls
    ):
        """Test 9: Filing.sections stored as dict (JSON-serializable from FilingSections.model_dump)."""
        from ai_washer.ingestion.filing_collector import FilingCollector

        mock_engine.return_value = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_session)

        filing = _make_filing_data()
        mock_client = MagicMock()
        mock_client.get_latest_filings.return_value = [filing]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_filing_cls.return_value = mock_client

        mock_xbrl = MagicMock()
        mock_xbrl.extract_company_xbrl.return_value = []
        mock_xbrl.__enter__ = MagicMock(return_value=mock_xbrl)
        mock_xbrl.__exit__ = MagicMock(return_value=False)
        mock_xbrl_cls.return_value = mock_xbrl

        app_settings = MagicMock()
        app_settings.edgar_identity = "Test test@test.com"
        collector = FilingCollector(app_settings=app_settings)

        collector.collect_for_company(
            company_id=uuid.uuid4(),
            cik="1234567",
            ticker="TEST",
        )

        # Find the Filing object in session.add calls
        filing_adds = [
            c[0][0]
            for c in mock_session.add.call_args_list
            if hasattr(c[0][0], "sections") and hasattr(c[0][0], "accession_no")
        ]
        assert len(filing_adds) >= 1
        assert isinstance(filing_adds[0].sections, dict)

    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_filing_collection_metadata_includes_version(
        self, mock_engine, mock_sf, mock_filing_cls, mock_xbrl_cls
    ):
        """Test 10: Filing.collection_metadata includes collector version and timestamp."""
        from ai_washer.ingestion.filing_collector import FilingCollector

        mock_engine.return_value = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_session)

        filing = _make_filing_data()
        mock_client = MagicMock()
        mock_client.get_latest_filings.return_value = [filing]
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_filing_cls.return_value = mock_client

        mock_xbrl = MagicMock()
        mock_xbrl.extract_company_xbrl.return_value = []
        mock_xbrl.__enter__ = MagicMock(return_value=mock_xbrl)
        mock_xbrl.__exit__ = MagicMock(return_value=False)
        mock_xbrl_cls.return_value = mock_xbrl

        app_settings = MagicMock()
        app_settings.edgar_identity = "Test test@test.com"
        collector = FilingCollector(app_settings=app_settings)

        collector.collect_for_company(
            company_id=uuid.uuid4(),
            cik="1234567",
            ticker="TEST",
        )

        filing_adds = [
            c[0][0]
            for c in mock_session.add.call_args_list
            if hasattr(c[0][0], "collection_metadata")
            and hasattr(c[0][0], "accession_no")
        ]
        assert len(filing_adds) >= 1
        metadata = filing_adds[0].collection_metadata
        assert "collector_version" in metadata
        assert "collected_at" in metadata


class TestFilingCollectorAll:
    """Tests for collect_all method."""

    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_collect_all_iterates_active_companies(
        self, mock_engine, mock_sf, mock_filing_cls, mock_xbrl_cls
    ):
        """Test 7: collect_all iterates active companies and calls collect_for_company."""
        from ai_washer.ingestion.filing_collector import FilingCollector

        mock_engine.return_value = MagicMock()

        company1 = _make_company_mock(ticker="AAPL", cik="320193")
        company2 = _make_company_mock(ticker="MSFT", cik="789019")

        # Session for collect_all query returns companies
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            company1,
            company2,
        ]
        # For collect_for_company inner sessions, return None (no existing records)
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_session)

        mock_client = MagicMock()
        mock_client.get_latest_filings.return_value = []
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_filing_cls.return_value = mock_client

        mock_xbrl = MagicMock()
        mock_xbrl.extract_company_xbrl.return_value = []
        mock_xbrl.__enter__ = MagicMock(return_value=mock_xbrl)
        mock_xbrl.__exit__ = MagicMock(return_value=False)
        mock_xbrl_cls.return_value = mock_xbrl

        app_settings = MagicMock()
        app_settings.edgar_identity = "Test test@test.com"
        collector = FilingCollector(app_settings=app_settings)

        results = collector.collect_all()

        assert len(results) == 2
        assert all(isinstance(r, CollectionResult) for r in results)

    @patch("ai_washer.ingestion.filing_collector.time")
    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_collect_all_rate_limits_between_companies(
        self, mock_engine, mock_sf, mock_filing_cls, mock_xbrl_cls, mock_time
    ):
        """Test 8: collect_all sleeps between companies for rate limiting."""
        from ai_washer.ingestion.filing_collector import FilingCollector

        mock_engine.return_value = MagicMock()

        company1 = _make_company_mock(ticker="AAPL", cik="320193")
        company2 = _make_company_mock(ticker="MSFT", cik="789019")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            company1,
            company2,
        ]
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_sf.return_value = MagicMock(return_value=mock_session)

        mock_client = MagicMock()
        mock_client.get_latest_filings.return_value = []
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_filing_cls.return_value = mock_client

        mock_xbrl = MagicMock()
        mock_xbrl.extract_company_xbrl.return_value = []
        mock_xbrl.__enter__ = MagicMock(return_value=mock_xbrl)
        mock_xbrl.__exit__ = MagicMock(return_value=False)
        mock_xbrl_cls.return_value = mock_xbrl

        app_settings = MagicMock()
        app_settings.edgar_identity = "Test test@test.com"
        collector = FilingCollector(app_settings=app_settings)

        collector.collect_all()

        # time.sleep was called at least once between companies
        assert mock_time.sleep.call_count >= 1
