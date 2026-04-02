"""Unit tests for the public Python API module.

All tests use mock sessions -- no real database required.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from ai_washer.api import get_latest_scores, get_score, get_score_history
from ai_washer.api_types import CompanyScore


def _make_company(
    ticker: str = "AAPL",
    name: str = "Apple Inc.",
    company_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock Company ORM object."""
    company = MagicMock()
    company.id = company_id or uuid.uuid4()
    company.ticker = ticker
    company.name = name
    return company


def _make_daily_score(
    company_id: uuid.UUID,
    composite_score: int = 55,
    confidence: float = 0.80,
    scored_at: datetime | None = None,
    signal_breakdown: dict | None = None,
    weights_used: dict | None = None,
    run_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock DailyScore ORM object."""
    row = MagicMock()
    row.company_id = company_id
    row.composite_score = composite_score
    row.confidence = confidence
    row.scored_at = scored_at or datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    row.signal_breakdown = signal_breakdown or {
        "sec_filing": 60,
        "patent_gap": 40,
        "github_activity": 50,
        "compute_spending": 70,
    }
    row.weights_used = weights_used or {
        "sec_filing": 0.25,
        "patent_gap": 0.20,
        "github_activity": 0.15,
        "compute_spending": 0.40,
    }
    row.run_id = run_id or uuid.uuid4()
    return row


def _make_signal_detail(
    company_id: uuid.UUID,
    signal_type: str,
    as_of_date: date,
) -> MagicMock:
    """Create a mock SignalDetail row for freshness queries."""
    row = MagicMock()
    row.signal_type = signal_type
    row.as_of_date = as_of_date
    return row


class TestGetScore:
    """Tests for get_score function."""

    def test_get_score_returns_company_score(self) -> None:
        """Mock DailyScore + Company rows, verify returns CompanyScore."""
        session = MagicMock()
        company_id = uuid.uuid4()
        company = _make_company(company_id=company_id)
        daily_score = _make_daily_score(company_id=company_id)

        # First execute: Company lookup
        # Second execute: DailyScore lookup
        # Third execute: signal freshness query
        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=daily_score)),
            MagicMock(all=MagicMock(return_value=[])),
        ]

        result = get_score("AAPL", session=session)

        assert result is not None
        assert isinstance(result, CompanyScore)
        assert result.ticker == "AAPL"
        assert result.company_name == "Apple Inc."
        assert result.composite_score == 55
        assert result.confidence == 0.80
        assert result.risk_band in ("genuine", "mixed", "significant_risk", "strong_short")
        assert result.run_id == daily_score.run_id

    def test_get_score_no_score_returns_none(self) -> None:
        """No DailyScore row -> returns None."""
        session = MagicMock()
        company = _make_company()

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        result = get_score("AAPL", session=session)
        assert result is None

    def test_get_score_no_company_returns_none(self) -> None:
        """Ticker not found -> returns None."""
        session = MagicMock()

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        result = get_score("ZZZZ", session=session)
        assert result is None

    def test_get_score_defaults_to_latest(self) -> None:
        """No date param -> queries most recent scored_at."""
        session = MagicMock()
        company_id = uuid.uuid4()
        company = _make_company(company_id=company_id)
        daily_score = _make_daily_score(company_id=company_id)

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=daily_score)),
            MagicMock(all=MagicMock(return_value=[])),
        ]

        result = get_score("AAPL", session=session)

        assert result is not None
        # Called without score_date -> should query latest
        assert session.execute.call_count == 3

    def test_get_score_specific_date(self) -> None:
        """Date param -> queries that specific date."""
        session = MagicMock()
        company_id = uuid.uuid4()
        company = _make_company(company_id=company_id)
        target_date = date(2026, 3, 10)
        daily_score = _make_daily_score(
            company_id=company_id,
            scored_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        )

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=daily_score)),
            MagicMock(all=MagicMock(return_value=[])),
        ]

        result = get_score("AAPL", score_date=target_date, session=session)

        assert result is not None
        assert result.scored_at == datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)

    def test_get_score_case_insensitive_ticker(self) -> None:
        """'aapl' finds Company with ticker 'AAPL'."""
        session = MagicMock()
        company_id = uuid.uuid4()
        company = _make_company(ticker="AAPL", company_id=company_id)
        daily_score = _make_daily_score(company_id=company_id)

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=daily_score)),
            MagicMock(all=MagicMock(return_value=[])),
        ]

        result = get_score("aapl", session=session)

        assert result is not None
        assert result.ticker == "AAPL"


class TestGetLatestScores:
    """Tests for get_latest_scores function."""

    def test_get_latest_scores_returns_list(self) -> None:
        """3 companies with scores -> returns 3 CompanyScore sorted by composite desc."""
        session = MagicMock()

        company_ids = [uuid.uuid4() for _ in range(3)]
        companies = [
            _make_company(ticker="HIGH", name="High Co", company_id=company_ids[0]),
            _make_company(ticker="MED", name="Med Co", company_id=company_ids[1]),
            _make_company(ticker="LOW", name="Low Co", company_id=company_ids[2]),
        ]
        scores = [
            _make_daily_score(company_id=company_ids[0], composite_score=90),
            _make_daily_score(company_id=company_ids[1], composite_score=55),
            _make_daily_score(company_id=company_ids[2], composite_score=20),
        ]

        # Return (DailyScore, Company) tuples already sorted by composite desc
        rows = list(zip(scores, companies))
        session.execute.return_value = MagicMock(all=MagicMock(return_value=rows))

        # Freshness queries: one per company
        freshness_mock = MagicMock(all=MagicMock(return_value=[]))
        original_execute = session.execute.return_value

        call_count = [0]
        all_returns = [rows, [], [], []]  # First: main query; then 3 freshness queries

        def side_effect_execute(*_args, **_kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return MagicMock(all=MagicMock(return_value=all_returns[0]))
            return MagicMock(all=MagicMock(return_value=all_returns[idx]))

        session.execute.side_effect = side_effect_execute

        result = get_latest_scores(session=session)

        assert len(result) == 3
        assert all(isinstance(r, CompanyScore) for r in result)
        assert result[0].composite_score == 90
        assert result[1].composite_score == 55
        assert result[2].composite_score == 20

    def test_get_latest_scores_empty(self) -> None:
        """No scores -> returns empty list."""
        session = MagicMock()
        session.execute.return_value = MagicMock(all=MagicMock(return_value=[]))

        result = get_latest_scores(session=session)
        assert result == []


class TestGetScoreHistory:
    """Tests for get_score_history function."""

    def test_get_score_history_returns_date_range(self) -> None:
        """Ticker with 5 DailyScore rows in range -> returns 5 sorted by scored_at asc."""
        session = MagicMock()
        company_id = uuid.uuid4()
        company = _make_company(ticker="AAPL", company_id=company_id)

        daily_scores = [
            _make_daily_score(
                company_id=company_id,
                scored_at=datetime(2026, 3, i, 12, 0, 0, tzinfo=timezone.utc),
                composite_score=50 + i,
            )
            for i in range(1, 6)
        ]

        # First call: company lookup, second: score query
        call_count = [0]

        def side_effect_execute(*_args, **_kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=company))
            if idx == 1:
                return MagicMock(
                    scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=daily_scores)))
                )
            # Freshness queries
            return MagicMock(all=MagicMock(return_value=[]))

        session.execute.side_effect = side_effect_execute

        result = get_score_history(
            "AAPL",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            session=session,
        )

        assert len(result) == 5
        assert all(isinstance(r, CompanyScore) for r in result)
        # Should be in ascending order
        assert result[0].composite_score == 51
        assert result[4].composite_score == 55

    def test_get_score_history_empty_range(self) -> None:
        """No scores in date range -> returns empty list."""
        session = MagicMock()
        company_id = uuid.uuid4()
        company = _make_company(ticker="AAPL", company_id=company_id)

        call_count = [0]

        def side_effect_execute(*_args, **_kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=company))
            return MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            )

        session.execute.side_effect = side_effect_execute

        result = get_score_history(
            "AAPL",
            start_date=date(2020, 1, 1),
            end_date=date(2020, 12, 31),
            session=session,
        )

        assert result == []


class TestAPIContracts:
    """Tests for cross-cutting API contracts."""

    def test_all_api_functions_accept_optional_session(self) -> None:
        """Verify each function works with explicitly passed session."""
        session = MagicMock()

        # get_score with session
        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        result = get_score("AAPL", session=session)
        assert result is None

        # get_latest_scores with session
        session.execute.reset_mock()
        session.execute.return_value = MagicMock(all=MagicMock(return_value=[]))
        session.execute.side_effect = None
        result2 = get_latest_scores(session=session)
        assert result2 == []

        # get_score_history with session
        session.execute.reset_mock()
        call_count = [0]

        def side_effect(*_args, **_kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            return MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            )

        session.execute.side_effect = side_effect
        result3 = get_score_history("AAPL", date(2026, 1, 1), date(2026, 12, 31), session=session)
        assert result3 == []

    def test_company_score_has_signals_available_and_missing(self) -> None:
        """signal_breakdown with 4 keys -> signals_available=4, signals_missing=2."""
        session = MagicMock()
        company_id = uuid.uuid4()
        company = _make_company(company_id=company_id)

        # 4 signals present, 2 missing (earnings_vagueness, job_mismatch)
        daily_score = _make_daily_score(
            company_id=company_id,
            signal_breakdown={
                "sec_filing": 60,
                "patent_gap": 40,
                "github_activity": 50,
                "compute_spending": 70,
            },
        )

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=daily_score)),
            MagicMock(all=MagicMock(return_value=[])),
        ]

        result = get_score("AAPL", session=session)

        assert result is not None
        assert len(result.signals_available) == 4
        assert len(result.signals_missing) == 2
        assert "earnings_vagueness" in result.signals_missing
        assert "job_mismatch" in result.signals_missing

    def test_company_score_has_run_id(self) -> None:
        """Verify run_id from DailyScore is in returned CompanyScore."""
        session = MagicMock()
        company_id = uuid.uuid4()
        expected_run_id = uuid.uuid4()
        company = _make_company(company_id=company_id)
        daily_score = _make_daily_score(company_id=company_id, run_id=expected_run_id)

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=daily_score)),
            MagicMock(all=MagicMock(return_value=[])),
        ]

        result = get_score("AAPL", session=session)

        assert result is not None
        assert result.run_id == expected_run_id

    def test_company_score_has_signal_freshness(self) -> None:
        """Mock SignalDetail rows -> signal_freshness dict populated."""
        session = MagicMock()
        company_id = uuid.uuid4()
        company = _make_company(company_id=company_id)
        daily_score = _make_daily_score(company_id=company_id)

        freshness_rows = [
            (
                "sec_filing",
                date(2026, 3, 10),
            ),
            (
                "patent_gap",
                date(2026, 3, 5),
            ),
        ]

        session.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=company)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=daily_score)),
            MagicMock(all=MagicMock(return_value=freshness_rows)),
        ]

        result = get_score("AAPL", session=session)

        assert result is not None
        assert result.signal_freshness is not None
        assert result.signal_freshness["sec_filing"] == date(2026, 3, 10)
        assert result.signal_freshness["patent_gap"] == date(2026, 3, 5)
