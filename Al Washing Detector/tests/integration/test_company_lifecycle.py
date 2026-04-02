"""Integration tests for Company soft-remove lifecycle against real PostgreSQL.

Verifies that the soft-delete pattern (is_active=False with deactivation_reason)
works correctly end-to-end per D-10: companies are never physically deleted,
only deactivated, and can be reactivated.

Uses testcontainers PostgreSQL with Alembic migrations via conftest.py.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from ai_washer.db.models import Company


def _insert_company(
    db_session,
    ticker: str,
    is_active: bool = True,
    deactivation_reason: str | None = None,
) -> Company:
    """Helper to insert a Company into the session."""
    company = Company(
        id=uuid.uuid4(),
        ticker=ticker,
        name=f"{ticker} Corp",
        cik=str(hash(ticker) % 10_000_000),
        market_cap_cents=400_000_000_000,
        is_active=is_active,
        deactivation_reason=deactivation_reason,
        aliases={"cik": str(hash(ticker) % 10_000_000)},
    )
    db_session.add(company)
    db_session.flush()
    return company


class TestSoftRemove:
    """Tests for the soft-delete (deactivation) lifecycle per D-10."""

    def test_deactivate_company(self, db_session) -> None:
        """Deactivating a company sets is_active=False and records reason."""
        _insert_company(db_session, ticker="DEAC")

        # Deactivate
        company = db_session.execute(
            select(Company).where(Company.ticker == "DEAC")
        ).scalar_one()
        company.is_active = False
        company.deactivation_reason = "not_in_scan_2026-03-27"
        db_session.flush()

        # Reload and verify
        loaded = db_session.execute(
            select(Company).where(Company.ticker == "DEAC")
        ).scalar_one()

        assert loaded.is_active is False
        assert loaded.deactivation_reason == "not_in_scan_2026-03-27"

    def test_reactivate_company(self, db_session) -> None:
        """Reactivating a deactivated company restores is_active and clears reason."""
        _insert_company(
            db_session,
            ticker="REAC",
            is_active=False,
            deactivation_reason="not_in_scan_2026-03-01",
        )

        # Reactivate
        company = db_session.execute(
            select(Company).where(Company.ticker == "REAC")
        ).scalar_one()
        company.is_active = True
        company.deactivation_reason = None
        db_session.flush()

        # Reload and verify
        loaded = db_session.execute(
            select(Company).where(Company.ticker == "REAC")
        ).scalar_one()

        assert loaded.is_active is True
        assert loaded.deactivation_reason is None

    def test_deactivated_not_in_active_query(self, db_session) -> None:
        """Active-only query excludes deactivated companies."""
        _insert_company(db_session, ticker="ACT1", is_active=True)
        _insert_company(db_session, ticker="INA1", is_active=False)

        result = db_session.execute(
            select(Company).where(
                Company.is_active == True,  # noqa: E712
                Company.ticker.in_(["ACT1", "INA1"]),
            )
        ).scalars().all()

        tickers = [c.ticker for c in result]
        assert tickers == ["ACT1"]

    def test_company_never_deleted(self, db_session) -> None:
        """Deactivated companies still exist in the database per D-10.

        Even when is_active=False, the row must be retrievable.
        Companies are never physically deleted from the database.
        """
        _insert_company(
            db_session,
            ticker="NDEL",
            is_active=False,
            deactivation_reason="not_in_scan_2026-03-15",
        )

        loaded = db_session.execute(
            select(Company).where(Company.ticker == "NDEL")
        ).scalar_one_or_none()

        assert loaded is not None
        assert loaded.ticker == "NDEL"
        assert loaded.is_active is False
        assert loaded.deactivation_reason == "not_in_scan_2026-03-15"
