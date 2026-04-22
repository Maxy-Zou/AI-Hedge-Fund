"""Portfolio state loading for the Phase 6 risk manager.

Provides the immutable :class:`PortfolioSnapshot` Pydantic model and two
pure-query helpers over the append-only ``portfolio_positions`` table:

- :func:`load_portfolio` filters rows by ``as_of_date <= target`` and
  collapses to the latest snapshot per ticker. This enforces Pitfall 2
  temporal correctness (06-RESEARCH.md): the portfolio visible to any
  risk check is the state *as of* the analysis date, never the future.
- :func:`seed_portfolio_from_csv` reads a developer-owned CSV fixture and
  writes one ``PortfolioPosition`` per row for the given ``as_of_date``.
  Used by tests and by plan 06-06 integration fixtures.

Pitfall 6 convention: :class:`PortfolioSnapshot` is always *pre-trade* --
callers that want to check concentration after adding a candidate must
combine the candidate with the snapshot themselves. This module never
mutates the snapshot.

Threat mitigation T-06-03: SQLAlchemy ORM is used exclusively; no raw SQL
string concatenation. The loader's filter is fully parameterised.
"""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import PortfolioPosition


class PortfolioSnapshotPosition(BaseModel):
    """Immutable single-position row in a :class:`PortfolioSnapshot`."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    sector: str
    quantity: float
    cost_basis_cents: int
    current_value_cents: int
    instrument_type: str = "equity"


class PortfolioSnapshot(BaseModel):
    """Immutable portfolio state as of a business date (pre-trade).

    ``total_value_cents`` is the sum of ``current_value_cents`` across
    :attr:`positions`; it is the denominator used by the weight helpers
    below. An empty portfolio has ``total_value_cents == 0`` and all
    weight helpers return ``0.0`` rather than raising ``ZeroDivisionError``.
    """

    model_config = ConfigDict(frozen=True)

    as_of_date: str
    positions: list[PortfolioSnapshotPosition] = Field(default_factory=list)
    total_value_cents: int = Field(ge=0, default=0)

    def tickers(self) -> list[str]:
        """Tickers currently held in the portfolio (pre-trade)."""
        return [p.ticker for p in self.positions]

    def position_value_pct(self, ticker: str) -> float:
        """Percentage of portfolio value held in ``ticker`` (0.0 if absent)."""
        if self.total_value_cents == 0:
            return 0.0
        for p in self.positions:
            if p.ticker == ticker:
                return p.current_value_cents / self.total_value_cents * 100
        return 0.0

    def sector_weight_pct(self, sector: str) -> float:
        """Sum of percentage weight for all positions in ``sector``."""
        if self.total_value_cents == 0:
            return 0.0
        sector_value = sum(p.current_value_cents for p in self.positions if p.sector == sector)
        return sector_value / self.total_value_cents * 100

    def weights(self) -> dict[str, float]:
        """Per-ticker weight as a fraction of total value (empty dict if total is 0)."""
        if self.total_value_cents == 0:
            return {}
        return {p.ticker: p.current_value_cents / self.total_value_cents for p in self.positions}


def _normalise_as_of(value: str | date | datetime) -> datetime:
    """Convert loose date/datetime/string inputs to a UTC datetime.

    Naive datetimes are treated as UTC. Plain dates become midnight UTC.
    Strings are parsed via ``datetime.fromisoformat`` (ISO-8601 only).
    """
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def load_portfolio(db_session: Session, as_of_date: str | date | datetime) -> PortfolioSnapshot:
    """Load the portfolio snapshot visible *as of* ``as_of_date``.

    Filters ``portfolio_positions`` by ``as_of_date <= target`` (Pitfall 2
    temporal correctness), then collapses to the latest snapshot per
    ticker by walking the descending-ordered result and keeping the first
    row seen per ticker.
    """
    target = _normalise_as_of(as_of_date)
    rows = (
        db_session.query(PortfolioPosition)
        .filter(PortfolioPosition.as_of_date <= target)
        .order_by(PortfolioPosition.as_of_date.desc())
        .all()
    )

    latest: dict[str, PortfolioPosition] = {}
    for row in rows:
        if row.ticker not in latest:
            latest[row.ticker] = row

    positions = [
        PortfolioSnapshotPosition(
            ticker=row.ticker,
            sector=row.sector,
            quantity=row.quantity,
            cost_basis_cents=row.cost_basis_cents,
            current_value_cents=row.current_value_cents,
            instrument_type=row.instrument_type,
        )
        for row in latest.values()
    ]
    total_value_cents = sum(p.current_value_cents for p in positions)
    return PortfolioSnapshot(
        as_of_date=target.date().isoformat(),
        positions=positions,
        total_value_cents=total_value_cents,
    )


def seed_portfolio_from_csv(
    db_session: Session,
    csv_path: str | Path,
    as_of_date: str | date | datetime,
) -> int:
    """Seed the ``portfolio_positions`` table from a developer-owned CSV.

    Expected header:
        ``ticker,sector,quantity,cost_basis_cents,current_value_cents,instrument_type``

    All rows are written with the single ``as_of_date`` argument (append-only
    per CLAUDE.md). Returns the number of rows inserted.
    """
    target = _normalise_as_of(as_of_date)
    path = Path(csv_path)
    rows: list[PortfolioPosition] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for record in reader:
            rows.append(
                PortfolioPosition(
                    ticker=record["ticker"].strip(),
                    sector=record["sector"].strip(),
                    quantity=float(record["quantity"]),
                    cost_basis_cents=int(record["cost_basis_cents"]),
                    current_value_cents=int(record["current_value_cents"]),
                    instrument_type=record.get("instrument_type", "equity").strip() or "equity",
                    as_of_date=target,
                )
            )

    db_session.add_all(rows)
    db_session.commit()
    return len(rows)
