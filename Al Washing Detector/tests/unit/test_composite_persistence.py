"""Tests for DailyScore composite persistence in ScoringOrchestrator.

Verifies:
- persist_composite creates DailyScore row with correct fields
- Same-day re-run is idempotent (no duplicates)
- scored_at is timezone-aware UTC
- as_of_date matches scoring_date
- score_all persists composites for each company
- Composite results are logged
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from ai_washer.analysis.composite_scorer import CompositeResult
from ai_washer.analysis.types import SignalResult
from ai_washer.config import ScoringConfig
from ai_washer.db.models import DailyScore


@pytest.fixture()
def scoring_date() -> date:
    return date(2026, 3, 15)


@pytest.fixture()
def run_id() -> uuid.UUID:
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture()
def company_id() -> uuid.UUID:
    return uuid.UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture()
def sample_composite() -> CompositeResult:
    return CompositeResult(
        score=72,
        confidence=0.85,
        risk_band="significant_risk",
        signal_breakdown={"sec_filing": 80, "patent_gap": 60},
        weights_used={"sec_filing": 0.6, "patent_gap": 0.4},
        signals_available=["patent_gap", "sec_filing"],
        signals_missing=["compute_spending", "earnings_vagueness", "github_activity", "job_mismatch"],
    )


@pytest.fixture()
def mock_session() -> MagicMock:
    session = MagicMock()
    # Default: no existing row (execute().scalar_one_or_none() returns None)
    session.execute.return_value.scalar_one_or_none.return_value = None
    session.execute.return_value.scalars.return_value.all.return_value = []
    return session


@pytest.fixture()
def orchestrator(mock_session, scoring_date, run_id):
    from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

    return ScoringOrchestrator(
        session=mock_session,
        config=ScoringConfig(),
        scoring_date=scoring_date,
        run_id=run_id,
    )


class TestPersistComposite:
    """Tests for ScoringOrchestrator.persist_composite."""

    def test_persist_composite_creates_daily_score_row(
        self, orchestrator, mock_session, company_id, sample_composite, run_id
    ):
        """persist_composite adds a DailyScore with correct fields."""
        result = orchestrator.persist_composite(company_id, sample_composite)

        assert result is True
        assert mock_session.add.call_count == 1

        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, DailyScore)
        assert added_obj.composite_score == 72
        assert added_obj.signal_breakdown == {"sec_filing": 80, "patent_gap": 60}
        assert added_obj.confidence == 0.85
        assert added_obj.weights_used == {"sec_filing": 0.6, "patent_gap": 0.4}
        assert added_obj.run_id == run_id
        assert added_obj.company_id == company_id
        mock_session.flush.assert_called()

    def test_persist_composite_idempotent_same_day(
        self, orchestrator, mock_session, company_id, sample_composite
    ):
        """Same-day re-run returns False and does not add row."""
        # Simulate existing row found
        mock_session.execute.return_value.scalar_one_or_none.return_value = MagicMock(
            spec=DailyScore
        )

        result = orchestrator.persist_composite(company_id, sample_composite)

        assert result is False
        mock_session.add.assert_not_called()

    def test_persist_composite_sets_scored_at_utc(
        self, orchestrator, mock_session, company_id, sample_composite, scoring_date
    ):
        """scored_at should be timezone-aware UTC datetime matching scoring_date."""
        orchestrator.persist_composite(company_id, sample_composite)

        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj.scored_at, datetime)
        assert added_obj.scored_at.tzinfo is not None
        assert added_obj.scored_at.tzinfo == timezone.utc
        assert added_obj.scored_at.date() == scoring_date

    def test_persist_composite_sets_as_of_date(
        self, orchestrator, mock_session, company_id, sample_composite, scoring_date
    ):
        """as_of_date on DailyScore matches scoring_date."""
        orchestrator.persist_composite(company_id, sample_composite)

        added_obj = mock_session.add.call_args[0][0]
        assert added_obj.as_of_date == scoring_date


class TestComputeAndPersistComposite:
    """Tests for ScoringOrchestrator.compute_and_persist_composite."""

    def test_returns_none_when_no_signals(self, orchestrator, company_id):
        """Returns None and does not persist when signal_results is empty."""
        result = orchestrator.compute_and_persist_composite(company_id, [])
        assert result is None

    def test_computes_and_persists(self, orchestrator, mock_session, company_id):
        """Computes composite, persists DailyScore, returns CompositeResult."""
        signals = [
            SignalResult(signal_type="sec_filing", score=75, evidence={}),
            SignalResult(signal_type="patent_gap", score=50, evidence={}),
        ]

        result = orchestrator.compute_and_persist_composite(company_id, signals)

        assert result is not None
        assert isinstance(result, CompositeResult)
        assert 0 <= result.score <= 100
        # DailyScore should have been added
        assert mock_session.add.call_count == 1


class TestScoreAllPersistsComposites:
    """Tests for score_all composite persistence integration."""

    def test_score_all_persists_composites(self, mock_session, scoring_date, run_id):
        """score_all calls compute_and_persist_composite for each company."""
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        # Create two mock companies
        company1 = MagicMock()
        company1.id = uuid.UUID("11111111-0000-0000-0000-000000000001")
        company1.ticker = "AAA"
        company1.cik = "0001234"
        company1.is_active = True

        company2 = MagicMock()
        company2.id = uuid.UUID("11111111-0000-0000-0000-000000000002")
        company2.ticker = "BBB"
        company2.cik = "0005678"
        company2.is_active = True

        mock_session.execute.return_value.scalars.return_value.all.return_value = [
            company1,
            company2,
        ]
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        orch = ScoringOrchestrator(
            session=mock_session,
            config=ScoringConfig(),
            scoring_date=scoring_date,
            run_id=run_id,
        )

        # Patch score_company to return predictable results
        signal = SignalResult(signal_type="sec_filing", score=65, evidence={})
        with patch.object(orch, "score_company", return_value=[signal]):
            with patch.object(orch, "persist_signals", return_value=1):
                with patch.object(orch, "compute_and_persist_composite") as mock_cpc:
                    mock_cpc.return_value = CompositeResult(
                        score=65,
                        confidence=0.2,
                        risk_band="significant_risk",
                        signal_breakdown={"sec_filing": 65},
                        weights_used={"sec_filing": 1.0},
                        signals_available=["sec_filing"],
                        signals_missing=[],
                    )
                    orch.score_all()

        assert mock_cpc.call_count == 2
        assert mock_cpc.call_args_list[0] == call(company1.id, [signal])
        assert mock_cpc.call_args_list[1] == call(company2.id, [signal])

    def test_score_all_logs_composite_results(self, mock_session, scoring_date, run_id):
        """score_all logs composite_score and risk_band."""
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        company = MagicMock()
        company.id = uuid.UUID("11111111-0000-0000-0000-000000000001")
        company.ticker = "AAA"
        company.cik = "0001234"
        company.is_active = True

        mock_session.execute.return_value.scalars.return_value.all.return_value = [company]
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        orch = ScoringOrchestrator(
            session=mock_session,
            config=ScoringConfig(),
            scoring_date=scoring_date,
            run_id=run_id,
        )

        signal = SignalResult(signal_type="sec_filing", score=65, evidence={})

        with patch.object(orch, "score_company", return_value=[signal]):
            with patch.object(orch, "persist_signals", return_value=1):
                with patch(
                    "ai_washer.analysis.scoring_orchestrator.logger"
                ) as mock_logger:
                    orch.score_all()

        # Check that scoring_complete log includes composite_count
        scoring_complete_calls = [
            c for c in mock_logger.info.call_args_list if c[0][0] == "scoring_complete"
        ]
        assert len(scoring_complete_calls) == 1
        assert "composites_persisted" in scoring_complete_calls[0][1]
