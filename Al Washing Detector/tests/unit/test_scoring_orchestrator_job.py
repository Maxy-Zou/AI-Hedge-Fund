"""Tests for job mismatch signal integration in ScoringOrchestrator.

Verifies that score_company includes job_mismatch as the 6th signal,
handles missing data gracefully, and computes ghost_ratio from lifecycle data.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from ai_washer.analysis.types import SignalResult


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


def _make_job_posting(
    role_classification: str = "engineering",
    first_seen: date = date(2025, 6, 1),
    last_seen: date = date(2025, 12, 1),
    is_active: bool = True,
) -> MagicMock:
    """Create a mock JobPosting ORM row."""
    posting = MagicMock()
    posting.role_classification = role_classification
    posting.first_seen = first_seen
    posting.last_seen = last_seen
    posting.is_active = is_active
    return posting


def _build_mock_session_for_score_company(
    mock_session,
    filings_orm=None,
    rd_facts=None,
    capex_facts=None,
    patent_rows=None,
    gh_max_date=None,
    gh_repos=None,
    transcript_rows=None,
    job_postings=None,
):
    """Set up mock session execute side effects for score_company.

    score_company makes queries in order:
    1. filings (scalars().all())
    2. rd_facts (scalars().all())
    3. capex_facts (scalars().all())
    4. patent_counts (all())
    5. github max_date (scalar_one_or_none())
    6. earnings transcripts (scalars().all())
    7. job postings (scalars().all())
    """
    mock_filings = MagicMock()
    mock_filings.scalars.return_value.all.return_value = filings_orm or []

    mock_rd = MagicMock()
    mock_rd.scalars.return_value.all.return_value = rd_facts or []

    mock_capex = MagicMock()
    mock_capex.scalars.return_value.all.return_value = capex_facts or []

    mock_patents = MagicMock()
    mock_patents.all.return_value = patent_rows or []

    mock_gh = MagicMock()
    mock_gh.scalar_one_or_none.return_value = gh_max_date

    side_effects = [mock_filings, mock_rd, mock_capex, mock_patents, mock_gh]

    # If gh_max_date is not None, there's an additional query for repos
    if gh_max_date is not None:
        mock_gh_repos = MagicMock()
        mock_gh_repos.scalars.return_value.all.return_value = gh_repos or []
        side_effects.append(mock_gh_repos)

    # Earnings transcripts query
    mock_transcripts = MagicMock()
    mock_transcripts.scalars.return_value.all.return_value = transcript_rows or []
    side_effects.append(mock_transcripts)

    # Job postings query
    mock_jobs = MagicMock()
    mock_jobs.scalars.return_value.all.return_value = job_postings or []
    side_effects.append(mock_jobs)

    mock_session.execute.side_effect = side_effects
    return mock_session


class TestLoadJobPostings:
    """Test _load_job_postings returns correct counts and ghost_ratio."""

    def test_returns_none_for_no_postings(self, mock_session, company_id, scoring_date, run_id):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        result = orch._load_job_postings(company_id)
        assert result is None

    def test_returns_correct_counts(self, mock_session, company_id, scoring_date, run_id):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        postings = [
            _make_job_posting("engineering", date(2025, 6, 1)),
            _make_job_posting("engineering", date(2025, 7, 1)),
            _make_job_posting("marketing", date(2025, 6, 15)),
            _make_job_posting("ambiguous", date(2025, 8, 1)),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = postings
        mock_session.execute.return_value = mock_result

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        result = orch._load_job_postings(company_id)
        assert result is not None
        ai_roles, mkt_roles, total, ghost_rat = result
        assert ai_roles == 2
        assert mkt_roles == 1
        assert total == 4

    def test_ghost_ratio_calculation(self, mock_session, company_id, scoring_date, run_id):
        """2 active postings, 1 older than 90 days -> ghost_ratio=0.5."""
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        # scoring_date = 2025-12-31
        # ghost_days_threshold = 90 (default)
        # Posting first_seen 2025-06-01: (2025-12-31 - 2025-06-01).days = 213 > 90 -> ghost
        # Posting first_seen 2025-11-01: (2025-12-31 - 2025-11-01).days = 60 < 90 -> not ghost
        postings = [
            _make_job_posting("engineering", first_seen=date(2025, 6, 1), is_active=True),
            _make_job_posting("marketing", first_seen=date(2025, 11, 1), is_active=True),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = postings
        mock_session.execute.return_value = mock_result

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        result = orch._load_job_postings(company_id)
        assert result is not None
        _, _, _, ghost_rat = result
        assert ghost_rat == 0.5

    def test_ghost_ratio_zero_when_no_active(self, mock_session, company_id, scoring_date, run_id):
        """All inactive postings -> ghost_ratio=0.0."""
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        postings = [
            _make_job_posting("engineering", first_seen=date(2025, 6, 1), is_active=False),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = postings
        mock_session.execute.return_value = mock_result

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        result = orch._load_job_postings(company_id)
        assert result is not None
        _, _, _, ghost_rat = result
        assert ghost_rat == 0.0


class TestScoreCompanyIncludesJobMismatch:
    """score_company produces job_mismatch SignalResult when job data exists."""

    @patch("ai_washer.analysis.scoring_orchestrator.compute_job_mismatch_score")
    def test_score_company_includes_job_mismatch(
        self,
        mock_scorer,
        mock_session,
        company_id,
        scoring_date,
        run_id,
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        mock_scorer.return_value = SignalResult(
            signal_type="job_mismatch",
            score=72,
            evidence={"signal_version": "0.8.0"},
        )

        postings = [
            _make_job_posting("engineering", date(2025, 6, 1)),
            _make_job_posting("marketing", date(2025, 7, 1)),
        ]

        _build_mock_session_for_score_company(
            mock_session,
            job_postings=postings,
        )

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        results = orch.score_company(company_id, "TEST")

        signal_types = [r.signal_type for r in results]
        assert "job_mismatch" in signal_types


class TestScoreCompanyNoJobData:
    """score_company handles missing job data gracefully."""

    @patch("ai_washer.analysis.scoring_orchestrator.compute_job_mismatch_score")
    def test_no_job_data_skips_signal(
        self,
        mock_scorer,
        mock_session,
        company_id,
        scoring_date,
        run_id,
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        _build_mock_session_for_score_company(
            mock_session,
            job_postings=[],
        )

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        results = orch.score_company(company_id, "NODATA")

        signal_types = [r.signal_type for r in results]
        assert "job_mismatch" not in signal_types
        mock_scorer.assert_not_called()


class TestScoreCompanyJobMismatchInsufficientData:
    """score_company handles scorer returning None (e.g., no AI claims)."""

    @patch("ai_washer.analysis.scoring_orchestrator.compute_job_mismatch_score")
    def test_scorer_returns_none_skips_signal(
        self,
        mock_scorer,
        mock_session,
        company_id,
        scoring_date,
        run_id,
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        mock_scorer.return_value = None

        postings = [
            _make_job_posting("engineering", date(2025, 6, 1)),
        ]

        _build_mock_session_for_score_company(
            mock_session,
            job_postings=postings,
        )

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        results = orch.score_company(company_id, "TEST")

        signal_types = [r.signal_type for r in results]
        assert "job_mismatch" not in signal_types
