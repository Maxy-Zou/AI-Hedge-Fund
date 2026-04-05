"""Kalshi API clients: live-tier (SDK wrapper) and historical-tier (httpx).

Architecture: Two separate client classes handle distinct API surfaces.
A router (KalshiClientRouter) selects the correct client based on
market close_time vs the cutoff timestamp.

Pitfall to avoid: KalshiLiveClient.get_candlesticks() must pass series_ticker
as the FIRST positional arg to SDK get_market_candlesticks(), not market_ticker.
URL template: /series/{ticker}/markets/{market_ticker}/candlesticks
"""
from __future__ import annotations

import time
from datetime import datetime

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from kalshi_backtest.config import KalshiBacktestSettings
from kalshi_backtest.ingestion.cutoff import HistoricalCutoffResolver
from kalshi_backtest.ingestion.types import CandlestickRecord, MarketRecord

logger = structlog.get_logger(__name__)

_HISTORICAL_BASE = "https://api.elections.kalshi.com/trade-api/v2"
_DAILY_INTERVAL = 1440  # minutes


class _TokenBucket:
    """Simple token bucket for rate limiting API requests."""

    def __init__(self, rate_limit_rpm: int) -> None:
        self._interval = 60.0 / rate_limit_rpm  # seconds per request
        self._last_request = 0.0

    def consume(self) -> None:
        """Block until the next request is allowed."""
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last_request = time.monotonic()


class KalshiLiveClient:
    """Wraps the kalshi-python SDK for live-tier candlestick and market data.

    IMPORTANT: get_market_candlesticks() takes (ticker=series_ticker, market_ticker=...)
    The first param is series_ticker (e.g. 'KXBTC'), not market_ticker.
    Verified from SDK source: URL = /series/{ticker}/markets/{market_ticker}/candlesticks.

    Args:
        settings: KalshiBacktestSettings with credentials and API base URL.
    """

    def __init__(self, settings: KalshiBacktestSettings) -> None:
        from kalshi_python import ApiClient, Configuration
        from kalshi_python.api import MarketsApi

        config = Configuration(host=settings.api_base_url)
        api_client = ApiClient(configuration=config)
        api_client.set_kalshi_auth(
            key_id=settings.api_key_id,
            private_key_path=str(settings.private_key_path),
        )
        self._markets_api = MarketsApi(api_client)
        self._rate_bucket = _TokenBucket(settings.rate_limit_rpm)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def get_candlesticks(
        self,
        series_ticker: str,
        market_ticker: str,
        start_ts: int,
        end_ts: int,
    ) -> list[CandlestickRecord]:
        """Fetch daily candlesticks from the live tier SDK endpoint.

        Args:
            series_ticker: Series ticker (e.g. 'KXBTC') — FIRST param in SDK, NOT market_ticker.
            market_ticker: Specific market ticker (e.g. 'KXBTCD-25JAN31-T99999').
            start_ts: Start of range, Unix epoch.
            end_ts: End of range, Unix epoch.

        Returns:
            List of CandlestickRecord parsed from the SDK response.
        """
        self._rate_bucket.consume()
        raw = self._markets_api.get_market_candlesticks(
            ticker=series_ticker,        # CRITICAL: series_ticker, not market_ticker
            market_ticker=market_ticker,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=_DAILY_INTERVAL,
        )
        candlesticks = raw.candlesticks or []
        return [
            CandlestickRecord(
                ticker=market_ticker,
                ts=(
                    int(c.end_period_ts.timestamp())
                    if hasattr(c.end_period_ts, "timestamp")
                    else c.end_period_ts
                ),
                open_price=int(c.price) if c.price is not None else None,
                high_price=None,  # SDK Candlestick has price field, not OHLC
                low_price=None,
                close_price=int(c.price) if c.price is not None else 0,
                volume=int(c.volume) if c.volume is not None else None,
            )
            for c in candlesticks
        ]


class KalshiHistoricalClient:
    """Direct httpx calls to /trade-api/v2/historical/* endpoints.

    Used for markets settled before the cutoff timestamp. The SDK has
    zero coverage of historical endpoints — confirmed from SDK introspection.

    Args:
        settings: KalshiBacktestSettings with credentials.
    """

    def __init__(self, settings: KalshiBacktestSettings) -> None:
        from kalshi_python.api_client import KalshiAuth

        self._settings = settings
        self._http = httpx.Client(timeout=30.0)
        self._rate_bucket = _TokenBucket(settings.rate_limit_rpm)
        self._kalshi_auth = KalshiAuth(
            key_id=self._settings.api_key_id,
            private_key_path=str(self._settings.private_key_path),
        )

    def _get_auth_headers(self, method: str, url: str) -> dict[str, str]:
        """Build per-request RSA-PSS auth headers via the SDK's KalshiAuth signer.

        Must be called per request — KALSHI-ACCESS-TIMESTAMP embeds current time.
        Reusing headers across requests will cause 401 due to timestamp replay rejection.

        Args:
            method: HTTP method (e.g., "GET").
            url: Full URL being requested (path is extracted internally by KalshiAuth).

        Returns:
            Dict with KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE, KALSHI-ACCESS-TIMESTAMP.
        """
        return self._kalshi_auth.create_auth_headers(method, url)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
    )
    def get_candlesticks(
        self,
        market_ticker: str,
        start_ts: int,
        end_ts: int,
    ) -> list[CandlestickRecord]:
        """Fetch daily candlesticks from historical tier via direct httpx call.

        Args:
            market_ticker: Specific market ticker.
            start_ts: Start of range, Unix epoch.
            end_ts: End of range, Unix epoch.

        Returns:
            List of CandlestickRecord parsed from historical API JSON response.
        """
        self._rate_bucket.consume()
        url = f"{_HISTORICAL_BASE}/historical/markets/{market_ticker}/candlesticks"
        resp = self._http.get(
            url,
            params={"start_ts": start_ts, "end_ts": end_ts, "period_interval": _DAILY_INTERVAL},
            headers=self._get_auth_headers("GET", url),
        )
        resp.raise_for_status()
        data = resp.json()
        candlesticks = data.get("candlesticks", [])

        return [
            CandlestickRecord(
                ticker=market_ticker,
                ts=int(c["ts"]),
                open_price=c.get("open_price"),
                high_price=c.get("high_price"),
                low_price=c.get("low_price"),
                close_price=c.get("close_price", c.get("price", 0)),
                volume=c.get("volume"),
            )
            for c in candlesticks
        ]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
    )
    def get_markets(
        self,
        min_close_ts: int | None = None,
        max_close_ts: int | None = None,
        cursor: str | None = None,
    ) -> tuple[list[MarketRecord], str | None]:
        """Fetch a page of historical markets.

        Args:
            min_close_ts: Filter markets closing after this epoch.
            max_close_ts: Filter markets closing before this epoch.
            cursor: Pagination cursor from previous response.

        Returns:
            Tuple of (list of MarketRecord, next_cursor or None).
        """
        self._rate_bucket.consume()
        params: dict = {"limit": 200}
        if min_close_ts is not None:
            params["min_close_ts"] = min_close_ts
        if max_close_ts is not None:
            params["max_close_ts"] = max_close_ts
        if cursor is not None:
            params["cursor"] = cursor

        resp = self._http.get(
            f"{_HISTORICAL_BASE}/historical/markets",
            params=params,
            headers=self._get_auth_headers("GET", f"{_HISTORICAL_BASE}/historical/markets"),
        )
        resp.raise_for_status()
        data = resp.json()

        markets = []
        for m in data.get("markets", []):
            try:
                record = MarketRecord(
                    ticker=m["ticker"],
                    event_ticker=m.get("event_ticker", ""),
                    series_ticker=m.get("series_ticker", ""),
                    subtitle=m.get("subtitle") or m.get("yes_sub_title"),
                    open_time=m.get("open_time", m.get("open_ts", 0)),
                    close_time=m.get("close_time", m.get("close_ts", 0)),
                    expiration_time=m.get("expiration_time"),
                    status=m.get("status", "unknown"),
                    result=m.get("result") or None,
                )
                markets.append(record)
            except Exception:
                logger.warning("market_parse_error", ticker=m.get("ticker", "unknown"))
                continue

        return markets, data.get("cursor")

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._http.close()


class KalshiClientRouter:
    """Routes candlestick fetches to the correct client tier.

    Uses HistoricalCutoffResolver to determine whether a market's
    close_time is before the cutoff (historical tier) or after (live tier).

    Args:
        live_client: KalshiLiveClient instance.
        historical_client: KalshiHistoricalClient instance.
        cutoff_resolver: HistoricalCutoffResolver instance.
    """

    def __init__(
        self,
        live_client: KalshiLiveClient,
        historical_client: KalshiHistoricalClient,
        cutoff_resolver: HistoricalCutoffResolver,
    ) -> None:
        self._live = live_client
        self._historical = historical_client
        self._resolver = cutoff_resolver

    def get_candlesticks(
        self,
        series_ticker: str,
        market_ticker: str,
        market_close_time: datetime,
        start_ts: int,
        end_ts: int,
    ) -> list[CandlestickRecord]:
        """Fetch candlesticks, routing to correct tier based on close_time.

        Args:
            series_ticker: Series ticker (needed for live client).
            market_ticker: Specific market ticker.
            market_close_time: Market's close_time (naive UTC) for tier routing.
            start_ts: Start of range, Unix epoch.
            end_ts: End of range, Unix epoch.

        Returns:
            List of CandlestickRecord from the correct tier.
        """
        cutoff = self._resolver.resolve()

        if self._resolver.is_historical(market_close_time, cutoff):
            logger.debug("routing_historical", ticker=market_ticker)
            return self._historical.get_candlesticks(market_ticker, start_ts, end_ts)
        else:
            logger.debug("routing_live", ticker=market_ticker)
            return self._live.get_candlesticks(series_ticker, market_ticker, start_ts, end_ts)
