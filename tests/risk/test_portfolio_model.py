"""Tests for the PortfolioPosition SQLAlchemy model (Phase 6 RISK-03).

Verifies the append-only financial-time-series convention (CLAUDE.md) and
the per-(ticker, as_of_date) uniqueness contract that prevents duplicate
snapshots while permitting new rows for new business dates.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import PortfolioPosition


def test_creating_portfolio_position_row_succeeds(db_session: Session) -> None:
    """Test 1: A PortfolioPosition row can be inserted with the canonical fields."""
    position = PortfolioPosition(
        ticker="AAPL",
        sector="Technology",
        quantity=100.0,
        cost_basis_cents=15_000_000,
        current_value_cents=17_000_000,
        instrument_type="equity",
        as_of_date=datetime(2026, 3, 1, tzinfo=UTC),
    )
    db_session.add(position)
    db_session.commit()

    stored = db_session.query(PortfolioPosition).filter_by(ticker="AAPL").one()
    assert stored.ticker == "AAPL"
    assert stored.sector == "Technology"
    assert stored.quantity == 100.0
    assert stored.cost_basis_cents == 15_000_000
    assert stored.current_value_cents == 17_000_000
    assert stored.instrument_type == "equity"


def test_duplicate_ticker_as_of_date_raises_integrity_error(db_session: Session) -> None:
    """Test 2: (ticker, as_of_date) uniqueness prevents same-snapshot duplicates.

    Append-only contract per CLAUDE.md: each business date is one row.
    """
    as_of = datetime(2026, 3, 1, tzinfo=UTC)
    row_a = PortfolioPosition(
        ticker="AAPL",
        sector="Technology",
        quantity=100.0,
        cost_basis_cents=15_000_000,
        current_value_cents=17_000_000,
        instrument_type="equity",
        as_of_date=as_of,
    )
    row_b = PortfolioPosition(
        ticker="AAPL",
        sector="Technology",
        quantity=50.0,
        cost_basis_cents=7_500_000,
        current_value_cents=8_500_000,
        instrument_type="equity",
        as_of_date=as_of,
    )
    db_session.add(row_a)
    db_session.commit()

    db_session.add(row_b)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_same_ticker_different_as_of_date_succeeds(db_session: Session) -> None:
    """Test 3: Append-only writes permitted across business dates.

    Closing or resizing writes a NEW row with a new as_of_date -- the
    append-only fund convention.
    """
    row_jan = PortfolioPosition(
        ticker="AAPL",
        sector="Technology",
        quantity=100.0,
        cost_basis_cents=15_000_000,
        current_value_cents=16_000_000,
        instrument_type="equity",
        as_of_date=datetime(2026, 1, 1, tzinfo=UTC),
    )
    row_feb = PortfolioPosition(
        ticker="AAPL",
        sector="Technology",
        quantity=150.0,
        cost_basis_cents=22_500_000,
        current_value_cents=24_000_000,
        instrument_type="equity",
        as_of_date=datetime(2026, 2, 1, tzinfo=UTC),
    )
    db_session.add_all([row_jan, row_feb])
    db_session.commit()

    rows = (
        db_session.query(PortfolioPosition)
        .filter(PortfolioPosition.ticker == "AAPL")
        .order_by(PortfolioPosition.as_of_date)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].quantity == 100.0
    assert rows[1].quantity == 150.0


def test_portfolio_position_has_expected_columns() -> None:
    """Test 4: Schema introspection -- all required columns are present."""
    columns = {c.name for c in PortfolioPosition.__table__.columns}
    required = {
        "id",
        "ticker",
        "sector",
        "quantity",
        "cost_basis_cents",
        "current_value_cents",
        "instrument_type",
        "as_of_date",
        "observed_date",
    }
    assert required.issubset(columns), f"Missing columns: {required - columns}"
