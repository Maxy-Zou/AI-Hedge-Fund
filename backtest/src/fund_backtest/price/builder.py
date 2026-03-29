"""PriceBuilder — orchestrates download and incremental update of OHLCV price data.

Mirrors the UniverseBuilder pattern:
- Accepts a session + optional PriceSettings
- download(): full 5-year load for all active universe tickers
- update(): incremental load from (last_date + 1) per ticker

Usage:
    from fund_backtest.price.builder import PriceBuilder
    builder = PriceBuilder(session=session)
    summary = builder.download()
    summary = builder.update()
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import structlog
from sqlalchemy.orm import Session

from fund_backtest.config import PriceSettings
from fund_backtest.db.models import UniverseTicker
from fund_backtest.price.downloader import download_in_chunks
from fund_backtest.price.repository import PriceBarRepository
from fund_backtest.price.types import (
    DownloadSummary,
    PriceAnomalyRecord,
    PriceBar,
)
from fund_backtest.price.validator import compute_coverage, detect_return_anomalies

log = structlog.get_logger(__name__)


class PriceBuilder:
    """Orchestrates a full price download or incremental update.

    Flow for download():
        1. Query active universe tickers from UniverseTicker
        2. download_in_chunks() — chunked yfinance requests over 5-year window
        3. detect_return_anomalies() per ticker
        4. repo.insert_bars() — ON CONFLICT DO NOTHING, safe to re-run
        5. repo.insert_anomalies()
        6. compute_coverage() and warn if below threshold
        7. Return DownloadSummary

    Flow for update():
        1. Query active universe tickers
        2. repo.get_last_dates() — find per-ticker last bar_date
        3. Per ticker: start = last_date + 1 (or full lookback if no data)
        4. Group by start date and call download_in_chunks() per group
        5. Insert bars and anomalies, return DownloadSummary

    All monetary/financial data is append-only — never modified after insert.

    Args:
        session: SQLAlchemy Session bound to the target database.
        settings: Optional PriceSettings; uses defaults if not provided.
    """

    def __init__(self, session: Session, settings: PriceSettings | None = None) -> None:
        self._session = session
        self._settings = settings or PriceSettings()
        self._repo = PriceBarRepository(session)

    def _get_active_tickers(self) -> list[str]:
        """Query all active tickers from universe_tickers table.

        Returns:
            List of ticker symbols where is_active=True.
        """
        rows = self._session.query(UniverseTicker.ticker).filter_by(is_active=True).all()
        return [r.ticker for r in rows]

    def _process_ticker_df(
        self,
        ticker: str,
        ticker_df: pd.DataFrame,
    ) -> tuple[list[PriceBar], list[PriceAnomalyRecord]]:
        """Convert a per-ticker DataFrame to PriceBar list and detect anomalies.

        Args:
            ticker: Exchange symbol.
            ticker_df: DataFrame with OHLCV columns and DatetimeIndex.

        Returns:
            Tuple of (bars, anomalies) for this ticker.
        """
        bars: list[PriceBar] = []
        for bar_date, row in ticker_df.iterrows():
            bd = bar_date.date() if hasattr(bar_date, "date") else bar_date
            try:
                bar = PriceBar.from_yfinance_row(ticker, bd, row)
                bars.append(bar)
            except Exception as exc:
                log.warning(
                    "bar_parse_failed",
                    ticker=ticker,
                    date=str(bd),
                    error=str(exc),
                )
        anomalies = detect_return_anomalies(
            ticker, ticker_df, self._settings.return_anomaly_threshold
        )
        return bars, anomalies

    def download(self, dry_run: bool = False) -> DownloadSummary:
        """Download 5 years of OHLCV bars for all active universe tickers.

        Uses ON CONFLICT DO NOTHING — safe to re-run on populated DB.
        Anomalous bars are stored in price_anomalies for downstream review.

        Args:
            dry_run: When True, logs a preview and returns without writing to DB.

        Returns:
            DownloadSummary with requested, successful, failed, bars_inserted counts.
        """
        tickers = self._get_active_tickers()
        if not tickers:
            log.warning("download_skipped_empty_universe")
            return DownloadSummary(requested=0, successful=[], failed=[], bars_inserted=0)

        start = date.today() - timedelta(days=self._settings.lookback_years * 365)
        log.info(
            "download_started",
            ticker_count=len(tickers),
            start=str(start),
            dry_run=dry_run,
        )

        if dry_run:
            log.info("dry_run_download_preview", tickers=tickers[:5], total=len(tickers))
            return DownloadSummary(
                requested=len(tickers), successful=[], failed=[], bars_inserted=0
            )

        results = download_in_chunks(
            tickers=tickers,
            start=start,
            batch_size=self._settings.batch_size,
            batch_sleep_secs=self._settings.batch_sleep_secs,
        )

        successful: list[str] = []
        all_bars: list[PriceBar] = []
        all_anomalies: list[PriceAnomalyRecord] = []

        for ticker, ticker_df in results:
            bars, anomalies = self._process_ticker_df(ticker, ticker_df)
            if bars:
                successful.append(ticker)
                all_bars.extend(bars)
                all_anomalies.extend(anomalies)

        failed = [t for t in tickers if t not in successful]
        bars_inserted = self._repo.insert_bars(all_bars)
        self._repo.insert_anomalies(all_anomalies)

        coverage = compute_coverage(tickers, successful, self._settings.coverage_alert_threshold)
        if coverage.below_threshold:
            log.warning(
                "coverage_below_threshold",
                coverage_pct=coverage.coverage_pct,
                threshold=self._settings.coverage_alert_threshold * 100,
                failed_count=coverage.failed,
            )

        log.info(
            "download_complete",
            requested=len(tickers),
            successful=len(successful),
            failed=len(failed),
            bars_inserted=bars_inserted,
            anomalies_flagged=len(all_anomalies),
        )
        return DownloadSummary(
            requested=len(tickers),
            successful=successful,
            failed=failed,
            bars_inserted=bars_inserted,
        )

    def update(self) -> DownloadSummary:
        """Append new bars since last download. Never modifies historical data.

        Each ticker is downloaded from (its last bar_date + 1 day) to today.
        Tickers with no bars at all receive the full lookback_years download.
        Tickers already up to date (last_date == today) are counted as successful.

        Returns:
            DownloadSummary with requested, successful, failed, bars_inserted counts.
        """
        tickers = self._get_active_tickers()
        if not tickers:
            return DownloadSummary(requested=0, successful=[], failed=[], bars_inserted=0)

        last_dates = self._repo.get_last_dates(tickers)
        full_history_start = date.today() - timedelta(days=self._settings.lookback_years * 365)

        # Determine per-ticker start date
        ticker_starts: dict[str, date] = {}
        for ticker in tickers:
            if ticker in last_dates:
                ticker_starts[ticker] = last_dates[ticker] + timedelta(days=1)
            else:
                ticker_starts[ticker] = full_history_start

        # Group tickers by start date to minimise API calls:
        # tickers sharing the same start date are batched together.
        start_groups: dict[date, list[str]] = {}
        for ticker, start in ticker_starts.items():
            start_groups.setdefault(start, []).append(ticker)

        successful: list[str] = []
        all_bars: list[PriceBar] = []
        all_anomalies: list[PriceAnomalyRecord] = []

        today = date.today()
        for start, group_tickers in start_groups.items():
            if start > today:
                # Already up to date — no new bars to fetch
                successful.extend(group_tickers)
                continue
            results = download_in_chunks(
                tickers=group_tickers,
                start=start,
                batch_size=self._settings.batch_size,
                batch_sleep_secs=self._settings.batch_sleep_secs,
            )
            for ticker, ticker_df in results:
                bars, anomalies = self._process_ticker_df(ticker, ticker_df)
                if bars:
                    successful.append(ticker)
                    all_bars.extend(bars)
                    all_anomalies.extend(anomalies)

        failed = [t for t in tickers if t not in successful]
        bars_inserted = self._repo.insert_bars(all_bars)
        self._repo.insert_anomalies(all_anomalies)

        coverage = compute_coverage(tickers, successful, self._settings.coverage_alert_threshold)
        if coverage.below_threshold:
            log.warning(
                "update_coverage_below_threshold",
                coverage_pct=coverage.coverage_pct,
                threshold=self._settings.coverage_alert_threshold * 100,
                failed_count=coverage.failed,
            )

        log.info(
            "update_complete",
            requested=len(tickers),
            successful=len(successful),
            failed=len(failed),
            bars_inserted=bars_inserted,
            anomalies_flagged=len(all_anomalies),
        )
        return DownloadSummary(
            requested=len(tickers),
            successful=successful,
            failed=failed,
            bars_inserted=bars_inserted,
        )
