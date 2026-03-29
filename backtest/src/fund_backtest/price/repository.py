"""Database access layer for price_bars and price_anomalies tables.

All mutations use ON CONFLICT DO NOTHING — historical rows are NEVER modified.
Provides:
    PriceBarRepository: CRUD operations for price_bars and price_anomalies
"""
from __future__ import annotations

import uuid
from datetime import date

import structlog
from sqlalchemy import text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from fund_backtest.db.models import PriceAnomalyORM, PriceBarORM
from fund_backtest.price.types import PriceAnomalyRecord, PriceBar

log = structlog.get_logger(__name__)


class PriceBarRepository:
    """Repository for price_bars and price_anomalies tables.

    All write operations use ON CONFLICT DO NOTHING — historical price rows
    are NEVER overwritten or deleted. This enforces the fund-wide immutability
    constraint for financial time-series data.

    Args:
        session: SQLAlchemy Session bound to the target database.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def insert_bars(self, bars: list[PriceBar]) -> int:
        """Bulk insert PriceBar records. Skips duplicates via ON CONFLICT DO NOTHING.

        Uses PostgreSQL upsert dialect to silently skip (ticker, bar_date) pairs
        that already exist. Historical rows are NEVER modified.

        Args:
            bars: List of PriceBar instances to persist.

        Returns:
            Count of rows actually inserted (does NOT include skipped duplicates).
        """
        if not bars:
            return 0
        rows = [
            {
                "id": uuid.uuid4(),
                "ticker": b.ticker,
                "bar_date": b.bar_date,
                "open_cents": b.open_cents,
                "high_cents": b.high_cents,
                "low_cents": b.low_cents,
                "close_cents": b.close_cents,
                "volume": b.volume,
            }
            for b in bars
        ]
        stmt = (
            pg_insert(PriceBarORM)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["ticker", "bar_date"])
            .returning(PriceBarORM.id)
        )
        result = self._session.execute(stmt)
        self._session.commit()
        # Use len(result.all()) instead of rowcount: psycopg3 returns -1 for
        # multi-row ON CONFLICT DO NOTHING inserts.  RETURNING gives the exact
        # set of IDs actually inserted.
        inserted = len(result.all())
        log.info("insert_bars_complete", requested=len(bars), inserted=inserted)
        return inserted

    def insert_anomalies(self, anomalies: list[PriceAnomalyRecord]) -> int:
        """Insert anomaly records. Skips duplicates via ON CONFLICT DO NOTHING.

        Args:
            anomalies: List of PriceAnomalyRecord instances to persist.

        Returns:
            Count of anomaly rows actually inserted.
        """
        if not anomalies:
            return 0
        rows = [
            {
                "id": uuid.uuid4(),
                "ticker": a.ticker,
                "bar_date": a.bar_date,
                "anomaly_type": a.anomaly_type,
                "daily_return_pct": a.daily_return_pct,
                "is_reviewed": False,
            }
            for a in anomalies
        ]
        stmt = (
            pg_insert(PriceAnomalyORM)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["ticker", "bar_date", "anomaly_type"])
            .returning(PriceAnomalyORM.id)
        )
        result = self._session.execute(stmt)
        self._session.commit()
        return len(result.all())

    def get_last_dates(self, tickers: list[str]) -> dict[str, date]:
        """Return {ticker: max(bar_date)} for all requested tickers that have bars.

        Tickers with no data are absent from the returned dict.

        Args:
            tickers: List of ticker symbols to look up.

        Returns:
            Mapping of ticker -> latest bar_date for tickers that have data.
        """
        if not tickers:
            return {}
        result = self._session.execute(
            text(
                "SELECT ticker, MAX(bar_date) AS last_date"
                " FROM price_bars"
                " WHERE ticker = ANY(:tickers)"
                " GROUP BY ticker"
            ),
            {"tickers": tickers},
        )
        return {row.ticker: row.last_date for row in result}

    def get_bars(
        self,
        tickers: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
        exclude_anomalies: bool = True,
    ) -> list[PriceBarORM]:
        """Fetch price bars for given tickers and date range.

        When exclude_anomalies=True, individual (ticker, bar_date) pairs with an
        unreviewed anomaly record are excluded from results. This is per-bar exclusion,
        NOT per-ticker exclusion — the rest of the ticker's history remains intact.

        Args:
            tickers: Ticker symbols to fetch.
            start_date: Inclusive lower bound on bar_date (None = no lower bound).
            end_date: Inclusive upper bound on bar_date (None = no upper bound).
            exclude_anomalies: When True, bars with unreviewed anomalies are hidden.

        Returns:
            List of PriceBarORM rows ordered by (ticker, bar_date).
        """
        query = self._session.query(PriceBarORM).filter(
            PriceBarORM.ticker.in_(tickers)
        )
        if start_date:
            query = query.filter(PriceBarORM.bar_date >= start_date)
        if end_date:
            query = query.filter(PriceBarORM.bar_date <= end_date)
        if exclude_anomalies:
            # Subquery: collect all (ticker, bar_date) pairs with unreviewed anomalies
            anomaly_pairs = (
                self._session.query(
                    PriceAnomalyORM.ticker,
                    PriceAnomalyORM.bar_date,
                )
                .filter(PriceAnomalyORM.is_reviewed.is_(False))
                .subquery()
            )
            # Exclude bars whose (ticker, bar_date) appears in the anomaly subquery.
            # tuple_ produces a SQL tuple comparison: NOT ((ticker, bar_date) IN (...))
            query = query.filter(
                ~tuple_(PriceBarORM.ticker, PriceBarORM.bar_date).in_(
                    self._session.query(
                        PriceAnomalyORM.ticker,
                        PriceAnomalyORM.bar_date,
                    ).filter(PriceAnomalyORM.is_reviewed.is_(False))
                )
            )
        return query.order_by(PriceBarORM.ticker, PriceBarORM.bar_date).all()

    def get_coverage_tickers(self) -> list[str]:
        """Return list of distinct tickers that have at least one price bar.

        Returns:
            Sorted list of ticker symbols present in price_bars.
        """
        result = self._session.execute(
            text("SELECT DISTINCT ticker FROM price_bars ORDER BY ticker")
        )
        return [row.ticker for row in result]
