"""IngestionPipeline: orchestrates the full Kalshi historical data ingestion run.

Wires together:
    MarketFetcher → fetches market records from Kalshi API
    CandlestickFetcher → fetches daily candles per market (incremental)
    MarketRepository → persists to DuckDB (append-only, idempotent)

Incremental sync (DATA-04): for each market, queries get_last_candle_ts() before
fetching. Only candles newer than the last stored timestamp are fetched.

Lookahead-safe writes (DATA-03): result column is ONLY written when
market.status == 'settled' — never for open or closed markets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import structlog

from kalshi_backtest.db.repository import MarketRepository
from kalshi_backtest.ingestion.fetcher import CandlestickFetcher, MarketFetcher
from kalshi_backtest.ingestion.types import MarketRecord


logger = structlog.get_logger(__name__)


@dataclass
class IngestionResult:
    """Summary of a completed ingestion run.

    Attributes:
        markets_upserted: Number of market records written.
        candles_inserted: Total candlestick rows inserted (skipped duplicates not counted).
        markets_failed: Tickers that encountered fetch errors (logged, not fatal).
        start_dt: Ingestion window start.
        end_dt: Ingestion window end.
        duration_seconds: Elapsed time for the run.
    """

    markets_upserted: int = 0
    candles_inserted: int = 0
    markets_failed: list[str] = field(default_factory=list)
    start_dt: datetime | None = None
    end_dt: datetime | None = None
    duration_seconds: float = 0.0


class IngestionPipeline:
    """Orchestrates a full ingestion run: fetch markets → fetch candles → store.

    Each call to run() is idempotent — re-running with the same date range
    produces no duplicate rows in the database.

    Args:
        market_fetcher: MarketFetcher instance for listing markets.
        candlestick_fetcher: CandlestickFetcher instance for per-market candles.
        repository: MarketRepository for DuckDB persistence.
    """

    def __init__(
        self,
        market_fetcher: MarketFetcher,
        candlestick_fetcher: CandlestickFetcher,
        repository: MarketRepository,
    ) -> None:
        self._market_fetcher = market_fetcher
        self._candle_fetcher = candlestick_fetcher
        self._repo = repository

    def run(
        self,
        lookback_days: int = 365,
        series_tickers: list[str] | None = None,
    ) -> IngestionResult:
        """Run a full ingestion pass.

        Steps:
        1. Compute date range: [now - lookback_days, now]
        2. Fetch all markets in range (no status filter — avoids survivorship bias)
        3. For each market: check last_candle_ts → fetch only newer candles
        4. Upsert market metadata + insert candles into DuckDB
        5. Only write result column for settled markets

        Args:
            lookback_days: Days of history to ingest (default 365).
            series_tickers: Optional list of series_ticker prefixes to filter
                            (e.g. ['KXBTC', 'PRES']). None = all series.

        Returns:
            IngestionResult with counts and failure list.
        """
        run_start = datetime.utcnow()
        end_dt = run_start
        start_dt = end_dt - timedelta(days=lookback_days)

        result = IngestionResult(start_dt=start_dt, end_dt=end_dt)

        log = logger.bind(lookback_days=lookback_days, start_dt=str(start_dt), end_dt=str(end_dt))
        log.info("ingestion_run_started")

        # Step 1: Fetch all markets in the date window
        markets = self._market_fetcher.fetch_all(start_dt, end_dt)

        # Step 2: Optional series_ticker filter (client-side, not API-side)
        if series_tickers:
            markets = [m for m in markets if m.series_ticker in series_tickers]
            log.info("markets_filtered_by_series", count=len(markets))

        log.info("markets_fetched_total", count=len(markets))

        # Step 3: Per-market candle ingestion
        for market in markets:
            try:
                # LOOKAHEAD PROTECTION: only write result when truly settled
                safe_result = market.result if market.status == "settled" else None
                safe_market = market.model_copy(update={"result": safe_result})
                self._repo.upsert_market(safe_market)
                result.markets_upserted += 1

                # Incremental sync: only fetch candles newer than last stored
                last_ts = self._repo.get_last_candle_ts(market.ticker)

                candles = self._candle_fetcher.fetch_for_market(
                    market=market,
                    lookback_start=start_dt,
                    last_ingested_ts=last_ts,
                )

                if candles:
                    self._repo.insert_candles(candles)
                    result.candles_inserted += len(candles)
                    log.debug(
                        "market_ingested",
                        ticker=market.ticker,
                        candles=len(candles),
                        incremental=(last_ts is not None),
                    )

            except Exception:
                logger.warning(
                    "market_ingestion_failed",
                    ticker=market.ticker,
                    exc_info=True,
                )
                result.markets_failed.append(market.ticker)

        result.duration_seconds = (datetime.utcnow() - run_start).total_seconds()
        log.info(
            "ingestion_run_complete",
            markets_upserted=result.markets_upserted,
            candles_inserted=result.candles_inserted,
            failures=len(result.markets_failed),
            duration_s=result.duration_seconds,
        )
        return result
