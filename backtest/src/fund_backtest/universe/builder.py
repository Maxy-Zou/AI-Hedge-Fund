"""UniverseBuilder — orchestrates seeder, enricher, and DB upsert.

Coordinates the full universe refresh cycle:
1. Fetch S&P 400 constituents from Wikipedia (seeder)
2. Enrich with market cap and sector from yfinance (enricher)
3. Filter to mid-cap range ($2B-$10B)
4. Upsert into universe_tickers (never delete)
5. Deactivate tickers that no longer pass the filter
6. Append a UniverseSnapshot audit record

Usage:
    from fund_backtest.universe.builder import UniverseBuilder
    builder = UniverseBuilder(session=session)
    result = builder.refresh()
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone

import structlog
from sqlalchemy.orm import Session

from fund_backtest.config import UniverseSettings
from fund_backtest.db.models import UniverseSnapshot, UniverseTicker
from fund_backtest.universe.enricher import enrich_universe
from fund_backtest.universe.seeder import fetch_sp400_seed
from fund_backtest.universe.types import RefreshResult, SeedRow, UniverseEntry

log = structlog.get_logger(__name__)


class UniverseBuilder:
    """Orchestrates a full universe refresh cycle.

    Flow:
        1. fetch_sp400_seed() — Wikipedia table
        2. enrich_universe() — yfinance market cap + sector
        3. filter by market cap range
        4. upsert into universe_tickers (never delete rows)
        5. deactivate tickers that no longer pass filter (set is_active=False)
        6. append a UniverseSnapshot row

    All monetary values stored as integer cents (not dollars/floats).
    Historical rows are never deleted — set is_active=False instead.
    """

    def __init__(self, session: Session, settings: UniverseSettings | None = None) -> None:
        """Initialize the builder with a database session and optional settings.

        Args:
            session: SQLAlchemy Session for database operations.
            settings: Optional UniverseSettings. Uses defaults if None.
        """
        self._session = session
        self._settings = settings or UniverseSettings()

    def refresh(self) -> RefreshResult:
        """Run a full universe refresh. Returns summary of changes.

        Returns:
            RefreshResult with new_count, removed_count, active_count, and sector_breakdown.
        """
        today = date.today()

        # 1. Seed from Wikipedia
        seed_df = fetch_sp400_seed(self._settings.seed_url)
        seed_rows = [SeedRow(**row) for row in seed_df.to_dict(orient="records")]
        log.info("seed_fetched", count=len(seed_rows))

        # 2. Enrich with yfinance
        entries = enrich_universe(seed_rows, delay_secs=self._settings.yfinance_delay_secs)

        # 3. Filter to mid-cap range
        in_range = [e for e in entries if e.is_in_midcap_range(self._settings)]
        log.info("market_cap_filtered", total=len(entries), in_range=len(in_range))

        # 4 & 5. Upsert and deactivate
        active_tickers_before = {
            row.ticker
            for row in self._session.query(UniverseTicker).filter_by(is_active=True).all()
        }
        in_range_tickers = {e.ticker for e in in_range}

        new_count = 0
        for entry in in_range:
            is_new = self._upsert_ticker(entry)
            if is_new:
                new_count += 1

        removed_count = 0
        for ticker in active_tickers_before - in_range_tickers:
            self._deactivate_ticker(ticker, reason="exited_midcap_range")
            removed_count += 1

        # 6. Snapshot
        sector_breakdown = dict(
            Counter(e.gics_sector for e in in_range if e.gics_sector)
        )
        snapshot = UniverseSnapshot(
            snapshot_date=today,
            active_count=len(in_range),
            new_count=new_count,
            removed_count=removed_count,
            sector_breakdown=sector_breakdown,
        )
        self._session.add(snapshot)
        self._session.commit()

        return RefreshResult(
            snapshot_date=today.isoformat(),
            active_count=len(in_range),
            new_count=new_count,
            removed_count=removed_count,
            sector_breakdown=sector_breakdown,
        )

    def _upsert_ticker(self, entry: UniverseEntry) -> bool:
        """Insert or update a UniverseTicker row.

        Never deletes rows — updates existing ones or inserts new ones.

        Args:
            entry: UniverseEntry with enriched ticker data.

        Returns:
            True if this is a new ticker (inserted), False if updated.
        """
        existing = (
            self._session.query(UniverseTicker).filter_by(ticker=entry.ticker).first()
        )
        now = datetime.now(tz=timezone.utc)

        if existing is None:
            new_row = UniverseTicker(
                ticker=entry.ticker,
                name=entry.name,
                gics_sector=entry.gics_sector,
                gics_sub_industry=entry.gics_sub_industry,
                market_cap_cents=entry.market_cap_cents,
                is_active=True,
                sector_source=entry.sector_source,
                last_refreshed_at=now,
            )
            self._session.add(new_row)
            return True

        # Update mutable fields — never delete the row
        existing.name = entry.name
        existing.gics_sector = entry.gics_sector
        existing.gics_sub_industry = entry.gics_sub_industry
        existing.market_cap_cents = entry.market_cap_cents
        existing.is_active = True
        existing.deactivation_reason = None
        existing.sector_source = entry.sector_source
        existing.last_refreshed_at = now
        return False

    def _deactivate_ticker(self, ticker: str, reason: str) -> None:
        """Mark a ticker as inactive. NEVER deletes the row.

        Args:
            ticker: Exchange symbol to deactivate.
            reason: Human-readable reason for deactivation (e.g. "exited_midcap_range").
        """
        existing = self._session.query(UniverseTicker).filter_by(ticker=ticker).first()
        if existing is not None:
            existing.is_active = False
            existing.deactivation_reason = reason
            log.info("ticker_deactivated", ticker=ticker, reason=reason)
