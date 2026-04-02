"""Integration test proving SignalDetail DB writes are persisted and queryable.

Uses testcontainers PostgreSQL fixture from conftest.py. Seeds Company,
Filing, and XBRLFact rows, then runs the scoring orchestrator and verifies
SignalDetail rows exist in the database (SCORE-02).
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from ai_washer.db.models import Company, Filing, SignalDetail, XBRLFact


@pytest.fixture
def test_company(db_session):
    """Seed a test company into the database."""
    company = Company(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        ticker="INTG",
        name="Integration Test Corp",
        cik="0009999999",
        sector="Technology",
        market_cap_cents=500_000_000_000,  # $5B
        is_active=True,
    )
    db_session.add(company)
    db_session.flush()
    return company


@pytest.fixture
def test_filings(db_session, test_company):
    """Seed 10-K filings spanning 4 years with realistic section text."""
    filings = []
    for year in range(2022, 2026):
        filing = Filing(
            company_id=test_company.id,
            form_type="10-K",
            accession_no=f"0009999999-{year}-000001",
            filing_date=date(year, 8, 15),
            period_of_report=date(year, 6, 30),
            sections={
                "mda": (
                    f"Year {year}: The company is deploying artificial intelligence "
                    f"and machine learning across operations. AI strategy drives growth. "
                    f"Deep learning models process customer data. Natural language processing "
                    f"powers chatbots. Neural network architecture scales efficiently. "
                ) * 20,  # Make it > 500 chars
                "risk_factors": (
                    f"Year {year}: AI technology risks include rapid evolution. "
                    f"Machine learning model drift may degrade performance. "
                    f"Artificial intelligence regulations may change. "
                ) * 20,
                "business": (
                    f"Year {year}: Our AI-powered solutions serve enterprise clients. "
                    f"Machine learning algorithms optimize supply chain. "
                    f"Artificial intelligence initiatives expand revenue. "
                ) * 20,
            },
            content_hash=f"hash_{year}",
            as_of_date=date(year, 6, 30),
        )
        filings.append(filing)
        db_session.add(filing)
    db_session.flush()
    return filings


@pytest.fixture
def test_xbrl_facts(db_session, test_company):
    """Seed R&D expense and CapEx XBRL facts for 4 years."""
    facts = []
    # R&D expense facts (growing modestly)
    for year, rd_cents in [
        (2022, 10_000_000_00),
        (2023, 11_000_000_00),
        (2024, 12_000_000_00),
        (2025, 13_000_000_00),
    ]:
        fact = XBRLFact(
            company_id=test_company.id,
            concept="rd_expense",
            tag="ResearchAndDevelopmentExpense",
            value_cents=rd_cents,
            fiscal_year=year,
            fiscal_period="FY",
            form_type="10-K",
            filed_date=date(year, 8, 15),
            end_date=date(year, 6, 30),
            accession_no=f"0009999999-{year}-000001",
            as_of_date=date(year, 6, 30),
        )
        facts.append(fact)
        db_session.add(fact)

    # CapEx facts (relatively flat)
    for year, capex_cents in [
        (2022, 5_000_000_00),
        (2023, 5_200_000_00),
        (2024, 5_100_000_00),
        (2025, 5_300_000_00),
    ]:
        fact = XBRLFact(
            company_id=test_company.id,
            concept="capex",
            tag="PaymentsToAcquirePropertyPlantAndEquipment",
            value_cents=capex_cents,
            fiscal_year=year,
            fiscal_period="FY",
            form_type="10-K",
            filed_date=date(year, 8, 15),
            end_date=date(year, 6, 30),
            accession_no=f"0009999999-{year}-000001",
            as_of_date=date(year, 6, 30),
        )
        facts.append(fact)
        db_session.add(fact)

    db_session.flush()
    return facts


class TestSignalPersistence:
    """Integration tests proving SignalDetail rows are persisted and queryable."""

    def test_scoring_produces_and_persists_signals(
        self, db_session, test_company, test_filings, test_xbrl_facts
    ):
        """Score a company and verify SignalDetail rows are written to DB."""
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        run_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        scoring_date = date(2025, 12, 31)

        orch = ScoringOrchestrator(
            session=db_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        results = orch.score_company(test_company.id, test_company.ticker)
        assert len(results) > 0, "Expected at least one signal result"

        inserted = orch.persist_signals(test_company.id, results)
        assert inserted > 0, "Expected at least one new signal row inserted"
        db_session.flush()

        # Query SignalDetail from a fresh select to prove persistence
        stmt = select(SignalDetail).where(
            SignalDetail.company_id == test_company.id
        )
        rows = db_session.execute(stmt).scalars().all()

        assert len(rows) > 0, "No SignalDetail rows found after scoring"

        for row in rows:
            assert row.signal_type in ("sec_filing", "compute_spending")
            assert 0 <= row.score <= 100
            assert isinstance(row.evidence, dict)
            assert len(row.evidence) > 0, "Evidence dict should not be empty"
            assert "signal_version" in row.evidence
            assert row.run_id == run_id

    def test_idempotent_rerun_no_duplicates(
        self, db_session, test_company, test_filings, test_xbrl_facts
    ):
        """Re-running scoring for same company+date should not create duplicates."""
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

        run_id = uuid.UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
        scoring_date = date(2025, 12, 31)

        orch = ScoringOrchestrator(
            session=db_session,
            scoring_date=scoring_date,
            run_id=run_id,
        )

        results = orch.score_company(test_company.id, test_company.ticker)
        first_count = orch.persist_signals(test_company.id, results)
        db_session.flush()

        # Count total rows after first run
        total_after_first = db_session.execute(
            select(func.count()).select_from(SignalDetail).where(
                SignalDetail.company_id == test_company.id,
                SignalDetail.as_of_date == scoring_date,
            )
        ).scalar()

        # Re-run with same scoring_date
        second_count = orch.persist_signals(test_company.id, results)
        db_session.flush()

        # Should have inserted zero new rows
        assert second_count == 0, f"Idempotent re-run inserted {second_count} rows"

        # Total count should not have changed
        total_after_second = db_session.execute(
            select(func.count()).select_from(SignalDetail).where(
                SignalDetail.company_id == test_company.id,
                SignalDetail.as_of_date == scoring_date,
            )
        ).scalar()

        assert total_after_second == total_after_first
