"""Tests for ScoringOrchestrator data conversion, scoring dispatch, and persistence.

Mocks the database session to test orchestrator logic without DB dependency.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from ai_washer.analysis.types import FilingForScoring, SignalResult


@pytest.fixture
def mock_session():
    """Create a mock SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def company_id():
    """Fixed company UUID for consistent tests."""
    return uuid.UUID("12345678-1234-1234-1234-123456789abc")


@pytest.fixture
def scoring_date():
    """Fixed scoring date for determinism."""
    return date(2025, 12, 31)


@pytest.fixture
def run_id():
    """Fixed run UUID for determinism."""
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def sample_filing_orm(company_id):
    """Create a mock Filing ORM object."""
    filing = MagicMock()
    filing.company_id = company_id
    filing.form_type = "10-K"
    filing.period_of_report = date(2025, 6, 30)
    filing.filing_date = date(2025, 8, 15)
    filing.sections = {
        "mda": "This company leverages artificial intelligence and machine learning.",
        "risk_factors": "AI technology risks include implementation challenges.",
        "business": "We are deploying AI solutions across business units.",
    }
    return filing


@pytest.fixture
def sample_filings_orm_multi_year(company_id):
    """Create mock Filing ORM objects spanning 3 years."""
    filings = []
    for year in range(2022, 2026):
        filing = MagicMock()
        filing.company_id = company_id
        filing.form_type = "10-K"
        filing.period_of_report = date(year, 6, 30)
        filing.filing_date = date(year, 8, 15)
        filing.sections = {
            "mda": f"Year {year}: artificial intelligence machine learning AI strategy.",
            "risk_factors": f"Year {year}: AI risk factors and technology challenges.",
            "business": f"Year {year}: AI solutions deployment across business units.",
        }
        filings.append(filing)
    return filings


@pytest.fixture
def sample_xbrl_rd_facts(company_id):
    """Create mock XBRLFact ORM objects for R&D expense."""
    facts = []
    for year, amount_cents in [
        (2022, 100_000_00),
        (2023, 120_000_00),
        (2024, 150_000_00),
        (2025, 180_000_00),
    ]:
        fact = MagicMock()
        fact.company_id = company_id
        fact.concept = "rd_expense"
        fact.fiscal_year = year
        fact.fiscal_period = "FY"
        fact.value_cents = amount_cents
        facts.append(fact)
    return facts


@pytest.fixture
def sample_xbrl_capex_facts(company_id):
    """Create mock XBRLFact ORM objects for CapEx."""
    facts = []
    for year, amount_cents in [
        (2022, 50_000_00),
        (2023, 55_000_00),
        (2024, 60_000_00),
        (2025, 65_000_00),
    ]:
        fact = MagicMock()
        fact.company_id = company_id
        fact.concept = "capex"
        fact.fiscal_year = year
        fact.fiscal_period = "FY"
        fact.value_cents = amount_cents
        facts.append(fact)
    return facts


class TestLoadFilings:
    """Test _load_filings converts Filing ORM objects to FilingForScoring."""

    def test_converts_filing_to_filing_for_scoring(
        self, mock_session, company_id, scoring_date, run_id, sample_filings_orm_multi_year
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        # Mock the session.execute().scalars().all() chain
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sample_filings_orm_multi_year
        mock_session.execute.return_value = mock_result

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        result = orch._load_filings(company_id)

        assert len(result) == 4
        assert all(isinstance(f, FilingForScoring) for f in result)
        assert result[0].year == 2022
        assert result[-1].year == 2025

    def test_uses_period_of_report_year(
        self, mock_session, company_id, scoring_date, run_id, sample_filing_orm
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_filing_orm]
        mock_session.execute.return_value = mock_result

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        filings = orch._load_filings(company_id)
        assert len(filings) == 1
        # period_of_report is 2025-06-30 => year 2025
        assert filings[0].year == 2025

    def test_falls_back_to_filing_date_year(self, mock_session, company_id, scoring_date, run_id):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        filing = MagicMock()
        filing.period_of_report = None
        filing.filing_date = date(2024, 3, 15)
        filing.sections = {"mda": "test"}

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [filing]
        mock_session.execute.return_value = mock_result

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        filings = orch._load_filings(company_id)
        assert filings[0].year == 2024


class TestScoreCompany:
    """Test score_company calls both scorers with correct inputs."""

    def test_calls_all_scorers(
        self,
        mock_session,
        company_id,
        scoring_date,
        run_id,
        sample_filings_orm_multi_year,
        sample_xbrl_rd_facts,
        sample_xbrl_capex_facts,
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        # Build separate mock results for filings, rd_facts, capex_facts, patent_counts
        mock_filings_result = MagicMock()
        mock_filings_result.scalars.return_value.all.return_value = sample_filings_orm_multi_year

        mock_rd_result = MagicMock()
        mock_rd_result.scalars.return_value.all.return_value = sample_xbrl_rd_facts

        mock_capex_result = MagicMock()
        mock_capex_result.scalars.return_value.all.return_value = sample_xbrl_capex_facts

        # Patent counts grouped by year (grant_year, cnt) tuples
        mock_patent_result = MagicMock()
        mock_patent_result.all.return_value = []
        mock_patent_result.__iter__ = MagicMock(return_value=iter([]))

        # GitHub max_date query returns None (no GitHub data)
        mock_gh_max_date = MagicMock()
        mock_gh_max_date.scalar_one_or_none.return_value = None

        # Earnings transcripts query returns empty
        mock_earnings_result = MagicMock()
        mock_earnings_result.scalars.return_value.all.return_value = []

        # Job postings query returns empty
        mock_jobs_result = MagicMock()
        mock_jobs_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [
            mock_filings_result,
            mock_rd_result,
            mock_capex_result,
            mock_patent_result,
            mock_gh_max_date,
            mock_earnings_result,
            mock_jobs_result,
        ]

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        results = orch.score_company(company_id, "TEST")

        # Should produce results (SEC and compute scorers should find data)
        assert isinstance(results, list)
        # Each result should be a SignalResult
        for r in results:
            assert isinstance(r, SignalResult)
            assert r.signal_type in (
                "sec_filing",
                "compute_spending",
                "patent_gap",
                "github_activity",
                "earnings_vagueness",
                "job_mismatch",
            )
            assert 0 <= r.score <= 100

    def test_returns_empty_list_for_no_filings(
        self, mock_session, company_id, scoring_date, run_id
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        mock_empty_scalars = MagicMock()
        mock_empty_scalars.scalars.return_value.all.return_value = []

        # Patent counts query returns empty list (no .scalars())
        mock_empty_rows = MagicMock()
        mock_empty_rows.all.return_value = []

        # GitHub max_date query returns None (no GitHub data)
        mock_gh_no_data = MagicMock()
        mock_gh_no_data.scalar_one_or_none.return_value = None

        # 7 queries: filings, rd_facts, capex_facts, patent_counts, github_max_date, earnings, jobs
        mock_session.execute.side_effect = [
            mock_empty_scalars,  # filings
            mock_empty_scalars,  # rd_facts
            mock_empty_scalars,  # capex_facts
            mock_empty_rows,  # patent_counts
            mock_gh_no_data,  # github_max_date
            mock_empty_scalars,  # earnings_transcripts
            mock_empty_scalars,  # job_postings
        ]

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        results = orch.score_company(company_id, "NODATA")
        assert results == []


class TestPersistSignals:
    """Test persist_signals creates SignalDetail rows correctly."""

    def test_creates_signal_detail(self, mock_session, company_id, scoring_date, run_id):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        results = [
            SignalResult(
                signal_type="sec_filing",
                score=65,
                evidence={"signal_version": "0.4.0", "test": True},
            ),
        ]

        # Mock no existing signal found (scalar_one_or_none returns None)
        mock_exists = MagicMock()
        mock_exists.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_exists

        count = orch.persist_signals(company_id, results)

        assert count == 1
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    def test_idempotent_skip_existing(self, mock_session, company_id, scoring_date, run_id):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        results = [
            SignalResult(
                signal_type="sec_filing",
                score=65,
                evidence={"signal_version": "0.4.0"},
            ),
        ]

        # Mock existing signal found
        mock_exists = MagicMock()
        mock_exists.scalar_one_or_none.return_value = MagicMock()  # existing row
        mock_session.execute.return_value = mock_exists

        count = orch.persist_signals(company_id, results)

        assert count == 0
        mock_session.add.assert_not_called()


class TestScoreCompanyPatentGap:
    """Test patent gap scoring integration in score_company."""

    def test_score_company_includes_patent_gap(
        self,
        mock_session,
        company_id,
        scoring_date,
        run_id,
        sample_filings_orm_multi_year,
        sample_xbrl_rd_facts,
        sample_xbrl_capex_facts,
    ):
        """Patent data present -> patent_gap signal included in results."""
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        mock_filings_result = MagicMock()
        mock_filings_result.scalars.return_value.all.return_value = sample_filings_orm_multi_year

        mock_rd_result = MagicMock()
        mock_rd_result.scalars.return_value.all.return_value = sample_xbrl_rd_facts

        mock_capex_result = MagicMock()
        mock_capex_result.scalars.return_value.all.return_value = sample_xbrl_capex_facts

        # Patent counts: mock rows with grant_year and cnt attributes
        patent_row_2022 = MagicMock()
        patent_row_2022.grant_year = 2022
        patent_row_2022.cnt = 5
        patent_row_2023 = MagicMock()
        patent_row_2023.grant_year = 2023
        patent_row_2023.cnt = 5
        patent_row_2024 = MagicMock()
        patent_row_2024.grant_year = 2024
        patent_row_2024.cnt = 5
        patent_row_2025 = MagicMock()
        patent_row_2025.grant_year = 2025
        patent_row_2025.cnt = 5

        mock_patent_result = MagicMock()
        mock_patent_result.all.return_value = [
            patent_row_2022,
            patent_row_2023,
            patent_row_2024,
            patent_row_2025,
        ]

        # GitHub max_date query returns None (no GitHub data)
        mock_gh_max_date = MagicMock()
        mock_gh_max_date.scalar_one_or_none.return_value = None

        # Earnings transcripts query returns empty
        mock_earnings_result = MagicMock()
        mock_earnings_result.scalars.return_value.all.return_value = []

        # Job postings query returns empty
        mock_jobs_result = MagicMock()
        mock_jobs_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [
            mock_filings_result,
            mock_rd_result,
            mock_capex_result,
            mock_patent_result,
            mock_gh_max_date,
            mock_earnings_result,
            mock_jobs_result,
        ]

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        results = orch.score_company(company_id, "TEST")

        signal_types = [r.signal_type for r in results]
        assert "patent_gap" in signal_types
        patent_result = next(r for r in results if r.signal_type == "patent_gap")
        assert 0 <= patent_result.score <= 100

    def test_score_company_skips_patent_gap_no_data(
        self,
        mock_session,
        company_id,
        scoring_date,
        run_id,
        sample_filings_orm_multi_year,
        sample_xbrl_rd_facts,
        sample_xbrl_capex_facts,
    ):
        """No Patent rows -> patent_gap signal skipped."""
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        mock_filings_result = MagicMock()
        mock_filings_result.scalars.return_value.all.return_value = sample_filings_orm_multi_year

        mock_rd_result = MagicMock()
        mock_rd_result.scalars.return_value.all.return_value = sample_xbrl_rd_facts

        mock_capex_result = MagicMock()
        mock_capex_result.scalars.return_value.all.return_value = sample_xbrl_capex_facts

        # Empty patent results
        mock_patent_result = MagicMock()
        mock_patent_result.all.return_value = []

        # GitHub max_date query returns None (no GitHub data)
        mock_gh_max_date = MagicMock()
        mock_gh_max_date.scalar_one_or_none.return_value = None

        # Earnings transcripts query returns empty
        mock_earnings_result = MagicMock()
        mock_earnings_result.scalars.return_value.all.return_value = []

        # Job postings query returns empty
        mock_jobs_result = MagicMock()
        mock_jobs_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [
            mock_filings_result,
            mock_rd_result,
            mock_capex_result,
            mock_patent_result,
            mock_gh_max_date,
            mock_earnings_result,
            mock_jobs_result,
        ]

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        results = orch.score_company(company_id, "TEST")

        signal_types = [r.signal_type for r in results]
        assert "patent_gap" not in signal_types


class TestScoreAll:
    """Test score_all iterates active companies."""

    def test_skips_companies_without_cik(self, mock_session, scoring_date, run_id):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        # Return one company with CIK and one without
        company_with_cik = MagicMock()
        company_with_cik.id = uuid.uuid4()
        company_with_cik.ticker = "GOOD"
        company_with_cik.cik = "0001234567"
        company_with_cik.is_active = True

        company_without_cik = MagicMock()
        company_without_cik.id = uuid.uuid4()
        company_without_cik.ticker = "NOCIK"
        company_without_cik.cik = None
        company_without_cik.is_active = True

        # The score_all query returns companies sorted by ticker
        # Only companies with CIK and is_active=True should be returned
        mock_companies_result = MagicMock()
        mock_companies_result.scalars.return_value.all.return_value = [company_with_cik]

        # 7 queries per company: filings, rd, capex, patents, github, earnings, jobs
        mock_empty_scalars = MagicMock()
        mock_empty_scalars.scalars.return_value.all.return_value = []
        mock_empty_rows = MagicMock()
        mock_empty_rows.all.return_value = []
        mock_gh_no_data = MagicMock()
        mock_gh_no_data.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [
            mock_companies_result,  # get active companies
            mock_empty_scalars,  # filings
            mock_empty_scalars,  # rd_facts
            mock_empty_scalars,  # capex_facts
            mock_empty_rows,  # patent_counts
            mock_gh_no_data,  # github_max_date
            mock_empty_scalars,  # earnings_transcripts
            mock_empty_scalars,  # job_postings
        ]

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        results = orch.score_all()
        # Should process one company (the one with CIK)
        assert len(results) == 1
        assert results[0][0] == "GOOD"
