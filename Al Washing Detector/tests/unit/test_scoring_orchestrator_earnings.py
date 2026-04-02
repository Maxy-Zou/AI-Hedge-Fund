"""Tests for earnings vagueness signal integration in ScoringOrchestrator.

Verifies that score_company includes earnings_vagueness as the 5th signal,
handles missing data gracefully, and passes correct ai_claim_intensity values.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from ai_washer.analysis.finbert_analyzer import SentimentResult
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


@pytest.fixture
def sample_transcript_text():
    """Sample transcript_text JSONB content (all values str | None)."""
    return {
        "full_text": (
            "We are leveraging ai in our ai transformation. "
            "Our gpu cluster runs the training pipeline with mlops."
        ),
        "prepared_remarks": "We see ai opportunity in digital transformation.",
        "qa": None,
    }


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
    """Helper to set up mock session execute side effects for score_company.

    Returns the mock_session configured with appropriate side_effect chain.
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


class TestScoreCompanyIncludesEarnings:
    """Test 1: score_company includes earnings_vagueness when transcripts exist."""

    @patch("ai_washer.analysis.scoring_orchestrator.FinBERTAnalyzer")
    @patch("ai_washer.analysis.scoring_orchestrator.compute_earnings_vagueness_score")
    def test_score_company_includes_earnings(
        self,
        mock_scorer,
        mock_finbert_cls,
        mock_session,
        company_id,
        scoring_date,
        run_id,
        sample_transcript_text,
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        # Create transcript ORM mock
        transcript = MagicMock()
        transcript.transcript_text = sample_transcript_text
        transcript.fiscal_year = 2025
        transcript.fiscal_quarter = 3

        # Set up FinBERT mock
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_text.return_value = SentimentResult(
            positive=0.5, negative=0.2, neutral=0.3
        )
        mock_finbert_cls.return_value = mock_analyzer

        # Set up scorer mock to return a SignalResult
        mock_scorer.return_value = SignalResult(
            signal_type="earnings_vagueness",
            score=55,
            evidence={"signal_version": "0.7.0"},
        )

        _build_mock_session_for_score_company(
            mock_session,
            transcript_rows=[transcript],
        )

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        results = orch.score_company(company_id, "TEST")

        signal_types = [r.signal_type for r in results]
        assert "earnings_vagueness" in signal_types


class TestScoreCompanyNoEarningsData:
    """Test 2: score_company logs signal_skipped when no transcripts exist."""

    @patch("ai_washer.analysis.scoring_orchestrator.compute_earnings_vagueness_score")
    def test_no_transcripts_skips_earnings(
        self, mock_scorer, mock_session, company_id, scoring_date, run_id
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        _build_mock_session_for_score_company(
            mock_session,
            transcript_rows=[],
        )

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        results = orch.score_company(company_id, "NODATA")

        signal_types = [r.signal_type for r in results]
        assert "earnings_vagueness" not in signal_types
        # Scorer should not have been called
        mock_scorer.assert_not_called()


class TestLoadEarningsTranscripts:
    """Test 3 & 4: _load_earnings_transcripts returns empty list or ordered dicts."""

    def test_returns_empty_for_no_transcripts(self, mock_session, company_id, scoring_date, run_id):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        result = orch._load_earnings_transcripts(company_id)
        assert result == []

    def test_returns_ordered_by_year_quarter_desc(
        self, mock_session, company_id, scoring_date, run_id
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        # Create transcripts in mixed order
        t1 = MagicMock()
        t1.fiscal_year = 2024
        t1.fiscal_quarter = 2
        t1.transcript_text = {"full_text": "Q2 2024"}

        t2 = MagicMock()
        t2.fiscal_year = 2025
        t2.fiscal_quarter = 1
        t2.transcript_text = {"full_text": "Q1 2025"}

        t3 = MagicMock()
        t3.fiscal_year = 2024
        t3.fiscal_quarter = 4
        t3.transcript_text = {"full_text": "Q4 2024"}

        mock_result = MagicMock()
        # DB returns ordered by fiscal_year desc, fiscal_quarter desc
        mock_result.scalars.return_value.all.return_value = [t2, t3, t1]
        mock_session.execute.return_value = mock_result

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        result = orch._load_earnings_transcripts(company_id)
        assert len(result) == 3
        assert result[0] == {"full_text": "Q1 2025"}
        assert result[1] == {"full_text": "Q4 2024"}
        assert result[2] == {"full_text": "Q2 2024"}


class TestAiClaimIntensityNoneWhenSecMissing:
    """Test 5: When SEC data missing, orchestrator passes ai_claim_intensity=None."""

    @patch("ai_washer.analysis.scoring_orchestrator.FinBERTAnalyzer")
    @patch("ai_washer.analysis.scoring_orchestrator.compute_earnings_vagueness_score")
    def test_sec_data_missing_passes_none(
        self,
        mock_scorer,
        mock_finbert_cls,
        mock_session,
        company_id,
        scoring_date,
        run_id,
        sample_transcript_text,
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        transcript = MagicMock()
        transcript.transcript_text = sample_transcript_text
        transcript.fiscal_year = 2025
        transcript.fiscal_quarter = 3

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_text.return_value = SentimentResult(
            positive=0.3, negative=0.3, neutral=0.4
        )
        mock_finbert_cls.return_value = mock_analyzer

        mock_scorer.return_value = SignalResult(
            signal_type="earnings_vagueness",
            score=50,
            evidence={"signal_version": "0.7.0"},
        )

        # No filings -> no keyword counts -> ai_claim_intensity should be None
        _build_mock_session_for_score_company(
            mock_session,
            filings_orm=[],
            transcript_rows=[transcript],
        )

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        orch.score_company(company_id, "TEST")

        # Verify compute_earnings_vagueness_score was called with ai_claim_intensity=None
        mock_scorer.assert_called_once()
        call_kwargs = mock_scorer.call_args
        # ai_claim_intensity should be None (not 0.0)
        assert call_kwargs.kwargs.get("ai_claim_intensity") is None or (
            len(call_kwargs.args) >= 3 and call_kwargs.args[2] is None
        )


class TestAiClaimIntensityZeroSkipsEarnings:
    """Test 6: When ai_claim_intensity=0.0, scorer returns None -> signal skipped."""

    @patch("ai_washer.analysis.scoring_orchestrator.FinBERTAnalyzer")
    @patch("ai_washer.analysis.scoring_orchestrator.compute_earnings_vagueness_score")
    def test_zero_intensity_skips_earnings(
        self,
        mock_scorer,
        mock_finbert_cls,
        mock_session,
        company_id,
        scoring_date,
        run_id,
        sample_transcript_text,
    ):
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        transcript = MagicMock()
        transcript.transcript_text = sample_transcript_text
        transcript.fiscal_year = 2025
        transcript.fiscal_quarter = 3

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_text.return_value = SentimentResult(
            positive=0.3, negative=0.3, neutral=0.4
        )
        mock_finbert_cls.return_value = mock_analyzer

        # Scorer returns None when ai_claim_intensity=0.0
        mock_scorer.return_value = None

        # Create filing data that produces ai_claim_intensity with 0.0 for scoring year
        filing = MagicMock()
        filing.period_of_report = date(2020, 6, 30)
        filing.filing_date = date(2020, 8, 15)
        filing.form_type = "10-K"
        filing.sections = {
            "mda": "no ai keywords here at all",
            "risk_factors": None,
            "business": None,
        }

        _build_mock_session_for_score_company(
            mock_session,
            filings_orm=[filing],
            transcript_rows=[transcript],
        )

        orch = ScoringOrchestrator(
            session=mock_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )
        results = orch.score_company(company_id, "TEST")

        signal_types = [r.signal_type for r in results]
        assert "earnings_vagueness" not in signal_types
