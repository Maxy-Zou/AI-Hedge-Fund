"""Integration tests for Company persistence against real PostgreSQL.

Verifies that Company rows with JSONB aliases survive round-trips through
a real PostgreSQL database (not SQLite), including JSONB-specific behavior
that unit tests with mocks cannot catch.

Uses testcontainers PostgreSQL with Alembic migrations via conftest.py.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from ai_washer.db.models import Company
from ai_washer.entity.types import (
    AliasesSchema,
    ResolutionMetadata,
    ResolutionMethod,
)


class TestCompanyPersistence:
    """Tests for persisting Company rows with JSONB aliases to PostgreSQL."""

    def test_new_company_inserted(self, db_session) -> None:
        """Insert a Company and verify all fields round-trip correctly."""
        aliases = AliasesSchema(
            cik="0001234567",
            patent_assignee=["Test Corp"],
            github_org=None,
            employer_names=["Test Corporation"],
            resolution_metadata=ResolutionMetadata(
                resolved_at="2026-03-27",
                method=ResolutionMethod.AUTOMATED_FUZZY,
                confidence=0.92,
                needs_review=False,
            ),
        )

        company = Company(
            id=uuid.uuid4(),
            ticker="TEST",
            name="TEST CORP",
            cik="1234567",
            market_cap_cents=500_000_000_000,
            is_active=True,
            aliases=aliases.model_dump(mode="json"),
        )
        db_session.add(company)
        db_session.flush()

        loaded = db_session.execute(
            select(Company).where(Company.ticker == "TEST")
        ).scalar_one()

        assert loaded.ticker == "TEST"
        assert loaded.name == "TEST CORP"
        assert loaded.cik == "1234567"
        assert loaded.market_cap_cents == 500_000_000_000
        assert loaded.is_active is True
        assert loaded.aliases["cik"] == "0001234567"
        assert loaded.aliases["patent_assignee"] == ["Test Corp"]
        assert loaded.aliases["github_org"] is None

    def test_aliases_jsonb_round_trip(self, db_session) -> None:
        """Verify AliasesSchema data survives JSONB serialization round-trip.

        Creates an AliasesSchema with full data including resolution_metadata,
        persists as JSONB, loads back, and re-parses with AliasesSchema.
        """
        original_aliases = AliasesSchema(
            cik="0009876543",
            patent_assignee=["Acme Corp", "Acme Technologies LLC"],
            github_org="acme-corp",
            employer_names=["Acme", "Acme Corporation"],
            resolution_metadata=ResolutionMetadata(
                resolved_at="2026-03-27",
                method=ResolutionMethod.AUTOMATED_FUZZY,
                confidence=0.88,
                needs_review=True,
            ),
        )

        company = Company(
            id=uuid.uuid4(),
            ticker="ACME",
            name="Acme Corp",
            cik="9876543",
            market_cap_cents=300_000_000_000,
            is_active=True,
            aliases=original_aliases.model_dump(mode="json"),
        )
        db_session.add(company)
        db_session.flush()

        loaded = db_session.execute(
            select(Company).where(Company.ticker == "ACME")
        ).scalar_one()

        # Re-parse from the JSONB dict back into the Pydantic schema
        parsed = AliasesSchema.model_validate(loaded.aliases)

        assert parsed.cik == "0009876543"
        assert parsed.patent_assignee == ["Acme Corp", "Acme Technologies LLC"]
        assert parsed.github_org == "acme-corp"
        assert parsed.employer_names == ["Acme", "Acme Corporation"]
        assert parsed.resolution_metadata is not None
        assert parsed.resolution_metadata.confidence == 0.88
        assert parsed.resolution_metadata.needs_review is True
        assert parsed.resolution_metadata.method == ResolutionMethod.AUTOMATED_FUZZY

    def test_multiple_companies_persisted(self, db_session) -> None:
        """Insert multiple companies in a batch and verify count."""
        for i in range(5):
            company = Company(
                id=uuid.uuid4(),
                ticker=f"T{i:03d}",
                name=f"Test Company {i}",
                cik=str(1000000 + i),
                market_cap_cents=200_000_000_000 + (i * 10_000_000_000),
                is_active=True,
                aliases={"cik": str(1000000 + i)},
            )
            db_session.add(company)

        db_session.flush()

        result = db_session.execute(
            select(Company).where(Company.ticker.like("T0%"))
        ).scalars().all()

        assert len(result) == 5
        tickers = sorted(c.ticker for c in result)
        assert tickers == ["T000", "T001", "T002", "T003", "T004"]
