"""Tests for PortfolioSnapshot + load_portfolio + seed_portfolio_from_csv.

Covers Phase 6 Pitfall 2 (temporal correctness) and Pitfall 6 (pre-trade
convention). PortfolioSnapshot is a frozen Pydantic model; ``load_portfolio``
filters by ``as_of_date <= target`` and collapses to the latest snapshot per
ticker; ``seed_portfolio_from_csv`` reads the fixture CSV and inserts rows.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import PortfolioPosition
from ai_hedge_fund.risk.portfolio import (
    PortfolioSnapshot,
    PortfolioSnapshotPosition,
    load_portfolio,
    seed_portfolio_from_csv,
)

# Self-contained fixture path (avoid cross-plan conftest coupling).
_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SAMPLE_CSV = _FIXTURES_DIR / "portfolio_sample.csv"


def test_portfolio_snapshot_minimal_instance_validates() -> None:
    """Test 1: PortfolioSnapshot accepts a minimal empty-portfolio instance."""
    snapshot = PortfolioSnapshot(as_of_date="2026-03-01", positions=[], total_value_cents=0)
    assert snapshot.positions == []
    assert snapshot.total_value_cents == 0
    assert snapshot.as_of_date == "2026-03-01"


def test_load_portfolio_empty_db_returns_empty_snapshot(db_session: Session) -> None:
    """Test 2: Empty DB yields PortfolioSnapshot with no positions, total_value_cents=0."""
    snapshot = load_portfolio(db_session, as_of_date=date(2026, 3, 1))
    assert snapshot.positions == []
    assert snapshot.total_value_cents == 0


def test_seed_portfolio_from_csv_inserts_five_rows(db_session: Session) -> None:
    """Test 3: seed_portfolio_from_csv inserts 5 PortfolioPosition rows."""
    inserted = seed_portfolio_from_csv(
        db_session,
        csv_path=_SAMPLE_CSV,
        as_of_date=datetime(2026, 3, 1, tzinfo=UTC),
    )
    assert inserted == 5

    rows = db_session.query(PortfolioPosition).all()
    assert len(rows) == 5
    tickers = {r.ticker for r in rows}
    assert tickers == {"AAPL", "MSFT", "JNJ", "JPM", "PG"}


def test_load_portfolio_after_seed_returns_five_positions(db_session: Session) -> None:
    """Test 4: After seeding, load_portfolio returns 5 SnapshotPosition entries."""
    seed_portfolio_from_csv(
        db_session,
        csv_path=_SAMPLE_CSV,
        as_of_date=datetime(2026, 3, 1, tzinfo=UTC),
    )
    snapshot = load_portfolio(db_session, as_of_date=date(2026, 3, 1))
    assert len(snapshot.positions) == 5
    for pos in snapshot.positions:
        assert isinstance(pos, PortfolioSnapshotPosition)


def test_load_portfolio_filters_by_as_of_date(db_session: Session) -> None:
    """Test 5: Pitfall 2 temporal correctness -- only positions with
    ``as_of_date <= target`` are returned."""
    seed_portfolio_from_csv(
        db_session,
        csv_path=_SAMPLE_CSV,
        as_of_date=datetime(2026, 1, 1, tzinfo=UTC),
    )

    # Query earlier than seed date -- no positions available yet.
    early = load_portfolio(db_session, as_of_date=date(2025, 6, 1))
    assert early.positions == []
    assert early.total_value_cents == 0

    # Query after seed date -- all 5 positions visible.
    later = load_portfolio(db_session, as_of_date=date(2026, 6, 1))
    assert len(later.positions) == 5
    assert later.total_value_cents > 0


def test_load_portfolio_collapses_to_latest_per_ticker(db_session: Session) -> None:
    """Test 6: Append-only + current-state semantics -- the latest row
    (by as_of_date <= target) per ticker wins."""
    # Seed AAPL twice with different as_of_dates.
    db_session.add(
        PortfolioPosition(
            ticker="AAPL",
            sector="Technology",
            quantity=10.0,
            cost_basis_cents=100_000,
            current_value_cents=110_000,
            instrument_type="equity",
            as_of_date=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    db_session.add(
        PortfolioPosition(
            ticker="AAPL",
            sector="Technology",
            quantity=20.0,
            cost_basis_cents=200_000,
            current_value_cents=250_000,
            instrument_type="equity",
            as_of_date=datetime(2026, 2, 1, tzinfo=UTC),
        )
    )
    db_session.commit()

    snapshot = load_portfolio(db_session, as_of_date=date(2026, 3, 1))
    aapl_positions = [p for p in snapshot.positions if p.ticker == "AAPL"]
    assert len(aapl_positions) == 1
    assert aapl_positions[0].quantity == 20.0
    assert aapl_positions[0].current_value_cents == 250_000


def test_sector_weight_pct_computes_concentration() -> None:
    """Test 7: sector_weight_pct sums each sector's value / total * 100.

    Empty portfolio (total = 0) returns 0.0 rather than raising.
    """
    snapshot = PortfolioSnapshot(
        as_of_date="2026-03-01",
        positions=[
            PortfolioSnapshotPosition(
                ticker="AAPL",
                sector="Technology",
                quantity=10.0,
                cost_basis_cents=100_000,
                current_value_cents=200_000,
            ),
            PortfolioSnapshotPosition(
                ticker="MSFT",
                sector="Technology",
                quantity=5.0,
                cost_basis_cents=150_000,
                current_value_cents=300_000,
            ),
            PortfolioSnapshotPosition(
                ticker="JNJ",
                sector="Healthcare",
                quantity=8.0,
                cost_basis_cents=100_000,
                current_value_cents=500_000,
            ),
        ],
        total_value_cents=1_000_000,
    )
    # Technology: (200_000 + 300_000) / 1_000_000 * 100 = 50.0
    assert snapshot.sector_weight_pct("Technology") == pytest.approx(50.0)
    # Healthcare: 500_000 / 1_000_000 * 100 = 50.0
    assert snapshot.sector_weight_pct("Healthcare") == pytest.approx(50.0)
    # Unknown sector: 0.0
    assert snapshot.sector_weight_pct("Energy") == pytest.approx(0.0)

    # Empty portfolio: 0.0, no ZeroDivisionError.
    empty = PortfolioSnapshot(as_of_date="2026-03-01", positions=[], total_value_cents=0)
    assert empty.sector_weight_pct("Technology") == pytest.approx(0.0)


def test_portfolio_snapshot_is_frozen() -> None:
    """Test 8: PortfolioSnapshot is immutable (frozen=True in ConfigDict)."""
    snapshot = PortfolioSnapshot(as_of_date="2026-03-01", positions=[], total_value_cents=0)
    with pytest.raises(ValidationError):
        snapshot.total_value_cents = 42  # type: ignore[misc]
