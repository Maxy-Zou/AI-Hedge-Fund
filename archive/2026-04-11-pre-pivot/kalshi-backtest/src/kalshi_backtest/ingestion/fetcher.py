"""High-level fetchers that page through Kalshi API responses.

MarketFetcher: Pages through all markets for a time range, returning MarketRecord list.
CandlestickFetcher: Fetches candlestick history for a single market ticker.

These fetchers wrap the low-level KalshiHistoricalClient/KalshiLiveClient with:
- Automatic pagination (cursor-based)
- Progress logging
- Survivorship-bias prevention (no status filter — fetch all markets)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import structlog

from kalshi_backtest.ingestion.client import KalshiClientRouter, KalshiHistoricalClient
from kalshi_backtest.ingestion.types import CandlestickRecord, MarketRecord

logger = structlog.get_logger(__name__)


class MarketFetcher:
    """Pages through historical markets for a date range.

    Fetches ALL markets in the range regardless of status — avoid survivorship bias
    by NOT filtering to status='settled'. The simulation engine decides what to include.

    Args:
        historical_client: KalshiHistoricalClient for market listing.
    """

    def __init__(self, historical_client: KalshiHistoricalClient) -> None:
        self._client = historical_client

    def fetch_all(
        self,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[MarketRecord]:
        """Fetch all markets closing within [start_dt, end_dt].

        Paginates automatically using cursor until exhausted.
        Does NOT filter by status — includes active, closed, settled, voided.

        Args:
            start_dt: Inclusive start of close_time range (naive UTC).
            end_dt: Inclusive end of close_time range (naive UTC).

        Returns:
            All MarketRecord objects in the range, deduplicated by ticker.
        """
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        all_markets: dict[str, MarketRecord] = {}
        cursor: str | None = None
        page = 0

        while True:
            markets, next_cursor = self._client.get_markets(
                min_close_ts=start_ts,
                max_close_ts=end_ts,
                cursor=cursor,
            )
            for m in markets:
                all_markets[m.ticker] = m

            page += 1
            logger.info(
                "market_page_fetched",
                page=page,
                count=len(markets),
                total_so_far=len(all_markets),
            )

            if next_cursor is None or not markets:
                break
            cursor = next_cursor

        return list(all_markets.values())


class CandlestickFetcher:
    """Fetches the complete candlestick history for a single market.

    Uses KalshiClientRouter to transparently handle live/historical tier split.
    Supports incremental sync by accepting an optional start timestamp.

    Args:
        router: KalshiClientRouter that selects live or historical client.
    """

    def __init__(self, router: KalshiClientRouter) -> None:
        self._router = router

    def fetch_for_market(
        self,
        market: MarketRecord,
        lookback_start: datetime,
        last_ingested_ts: int | None = None,
    ) -> list[CandlestickRecord]:
        """Fetch candlesticks for a market, supporting incremental sync.

        Args:
            market: MarketRecord to fetch candles for.
            lookback_start: Earliest date to fetch (used if no prior data exists).
            last_ingested_ts: Unix epoch of most recent stored candle. If provided,
                              fetches only newer candles (incremental sync — DATA-04).

        Returns:
            List of CandlestickRecord for the market, possibly empty if up to date.
        """
        # Incremental sync: start from day after last ingested candle
        if last_ingested_ts is not None:
            start_dt = datetime.utcfromtimestamp(last_ingested_ts) + timedelta(days=1)
        else:
            start_dt = lookback_start

        # Don't fetch beyond market's close_time
        end_dt = min(market.close_time, datetime.utcnow())

        if start_dt >= end_dt:
            logger.debug("candles_up_to_date", ticker=market.ticker)
            return []

        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        candles = self._router.get_candlesticks(
            series_ticker=market.series_ticker,
            market_ticker=market.ticker,
            market_close_time=market.close_time,
            start_ts=start_ts,
            end_ts=end_ts,
        )

        logger.info(
            "candles_fetched",
            ticker=market.ticker,
            count=len(candles),
            start=str(start_dt),
            end=str(end_dt),
        )
        return candles
