"""Tests for schema correctness -- column types, constraints, relationships.

Verifies that columns have correct types, constraints are enforced,
and basic CRUD operations work against the real database schema.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import inspect

pytestmark = pytest.mark.integration


def test_companies_columns(db_engine):
    """Verify companies table has expected columns."""
    inspector = inspect(db_engine)
    columns = {c["name"] for c in inspector.get_columns("companies")}
    expected = {
        "id",
        "ticker",
        "name",
        "cik",
        "sector",
        "market_cap_cents",
        "aliases",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(columns)


def test_companies_ticker_unique(db_engine):
    """Verify ticker has a unique constraint."""
    inspector = inspect(db_engine)
    unique_constraints = inspector.get_unique_constraints("companies")
    ticker_unique = any(
        "ticker" in uc.get("column_names", []) for uc in unique_constraints
    )
    assert ticker_unique


def test_signal_details_columns(db_engine):
    """Verify signal_details has dual timestamps."""
    inspector = inspect(db_engine)
    columns = {c["name"] for c in inspector.get_columns("signal_details")}
    assert "as_of_date" in columns  # D-08
    assert "observed_date" in columns  # D-08
    assert "signal_type" in columns
    assert "evidence" in columns  # D-05 JSONB


def test_pipeline_runs_columns(db_engine):
    """Verify pipeline_runs has expected columns."""
    inspector = inspect(db_engine)
    columns = {c["name"] for c in inspector.get_columns("pipeline_runs")}
    expected = {
        "id",
        "started_at",
        "ended_at",
        "status",
        "companies_processed",
        "errors",
        "created_at",
    }
    assert expected.issubset(columns)


def test_insert_company_and_query(db_session):
    """Verify basic insert and query works on companies table."""
    from ai_washer.db.models import Company

    company = Company(
        ticker="TEST",
        name="Test Corp",
        cik="0001234567",
        sector="Technology",
    )
    db_session.add(company)
    db_session.flush()

    result = db_session.query(Company).filter_by(ticker="TEST").first()
    assert result is not None
    assert result.name == "Test Corp"
    assert isinstance(result.id, uuid.UUID)


def test_insert_signal_detail(db_session):
    """Verify signal_detail insert with dual timestamps."""
    from ai_washer.db.models import Company, SignalDetail

    company = Company(ticker="SIG1", name="Signal Test Corp")
    db_session.add(company)
    db_session.flush()

    detail = SignalDetail(
        company_id=company.id,
        signal_type="sec_filing",
        score=75,
        evidence={"keywords": ["AI", "machine learning"]},
        run_id=uuid.uuid4(),
        as_of_date=date(2026, 3, 27),
    )
    db_session.add(detail)
    db_session.flush()

    result = (
        db_session.query(SignalDetail)
        .filter_by(company_id=company.id)
        .first()
    )
    assert result is not None
    assert result.score == 75
    assert result.as_of_date == date(2026, 3, 27)
    assert result.observed_date is not None  # server default


def test_insert_pipeline_run(db_session):
    """Verify pipeline_run insert and status default."""
    from ai_washer.db.models import PipelineRun

    run = PipelineRun()
    db_session.add(run)
    db_session.flush()

    result = db_session.query(PipelineRun).first()
    assert result is not None
    assert result.status == "running"
    assert result.companies_processed == 0
    assert result.errors == []
