"""Kalshi API client with RSA authentication, rate limiting, and politics filtering.

This is the single integration point with the Kalshi v2 REST API.
Authentication uses RSA-PSS per-request signing via the official kalshi-python SDK.
Rate limiting is enforced with a token bucket (DATA-05).
Market filtering uses an allowlist of series tickers (DATA-03) — there is no
'category' query param in the Kalshi API; filtering is post-fetch by series_ticker.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from threading import Lock

import structlog
from kalshi_python import ApiClient, Configuration
from kalshi_python.api import MarketsApi, PortfolioApi

from kalshi_tracker.config import KalshiSettings
from kalshi_tracker.kalshi.types import MarketSnapshot

logger = structlog.get_logger(__name__)


class RateLimitError(Exception):
    """Raised when the Kalshi API rate limit is exceeded."""


class _TokenBucket:
    """Thread-safe token bucket for rate limiting.

    Allows `rate_per_minute` tokens per 60-second window.
    consume() returns None if a token is available, raises RateLimitError otherwise.
    """

    def __init__(self, rate_per_minute: int) -> None:
        self._rate = rate_per_minute
        self._tokens = float(rate_per_minute)
        self._last_refill = time.monotonic()
        self._lock = Lock()

    def consume(self) -> None:
        """Consume one token. Raises RateLimitError if bucket is empty.

        Raises:
            RateLimitError: If no tokens are available.
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            # Refill tokens proportionally to elapsed time
            self._tokens = min(
                float(self._rate),
                self._tokens + elapsed * (self._rate / 60.0),
            )
            self._last_refill = now
            if self._tokens < 1.0:
                raise RateLimitError(
                    f"Rate limit exceeded ({self._rate} req/min). "
                    "Slow down polling or increase KALSHI_RATE_LIMIT_RPM."
                )
            self._tokens -= 1.0


class KalshiClient:
    """Kalshi v2 API client with RSA authentication, rate limiting, and politics filtering.

    Usage:
        settings = KalshiSettings()
        client = KalshiClient(settings)
        snapshots = client.get_politics_markets()  # list[MarketSnapshot]

    Authentication (DATA-01):
        Uses kalshi_python SDK's set_kalshi_auth() which loads the RSA PEM file and
        signs every request with RSA-PSS (SHA256). Headers added automatically:
        KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE, KALSHI-ACCESS-TIMESTAMP.

    Rate limiting (DATA-05):
        Token bucket enforces settings.rate_limit_rpm (default 60 req/min).
        Every API call consumes one token. Raises RateLimitError if exhausted.

    Market filtering (DATA-03):
        Fetches markets per series_ticker from settings.politics_series allowlist.
        There is NO category filter in the Kalshi API — filtering is done client-side.
    """

    def __init__(self, settings: KalshiSettings) -> None:
        """Initialize KalshiClient.

        Args:
            settings: KalshiSettings with API key ID, private key path, and base URL.
        """
        self._settings = settings
        self._rate_bucket = _TokenBucket(settings.rate_limit_rpm)

        config = Configuration(host=settings.api_base_url)
        self._api_client = ApiClient(configuration=config)
        # RSA-PSS auth: SDK loads PEM file and signs every request.
        # Do NOT pass PEM content — pass the file path. SDK reads it at startup.
        self._api_client.set_kalshi_auth(
            key_id=settings.api_key_id,
            private_key_path=str(settings.private_key_path),
        )
        self._markets_api = MarketsApi(self._api_client)
        self._portfolio_api = PortfolioApi(self._api_client)
        self._log = logger.bind(
            api_base_url=settings.api_base_url,
            rate_limit_rpm=settings.rate_limit_rpm,
        )
        self._log.info("kalshi_client_initialized")

    @property
    def portfolio_api(self) -> PortfolioApi:
        """Expose the authenticated PortfolioApi instance for live order placement.

        Reuses the same ApiClient (and RSA auth) already configured for this client.
        Used by the CLI to construct TradeExecutor in live mode without duplicating auth setup.

        Returns:
            PortfolioApi instance sharing this client's authentication configuration.
        """
        return self._portfolio_api

    def get_politics_markets(self) -> list[MarketSnapshot]:
        """Fetch all open politics/policy markets and return as typed snapshots.

        Fetches markets for each series ticker in settings.politics_series (allowlist).
        Handles pagination via SDK cursor. Filters out non-open markets.

        Returns:
            List of MarketSnapshot objects for all active politics/policy markets.

        Raises:
            RateLimitError: If the rate limit is exceeded during fetching.
        """
        captured_at = datetime.now(UTC)
        snapshots: list[MarketSnapshot] = []

        for series_ticker in self._settings.politics_series:
            series_snapshots = self._fetch_series_markets(series_ticker, captured_at)
            snapshots.extend(series_snapshots)
            self._log.info(
                "series_markets_fetched",
                series_ticker=series_ticker,
                count=len(series_snapshots),
            )

        self._log.info("politics_markets_fetched", total=len(snapshots))
        return snapshots

    def _fetch_series_markets(
        self,
        series_ticker: str,
        captured_at: datetime,
    ) -> list[MarketSnapshot]:
        """Fetch all open markets for a single series with pagination.

        Args:
            series_ticker: Kalshi series ticker (e.g., "PRES", "SENATE").
            captured_at: Timestamp to stamp all snapshots from this fetch.

        Returns:
            List of MarketSnapshot for this series.

        Raises:
            RateLimitError: If rate limit is exceeded.
        """
        snapshots: list[MarketSnapshot] = []
        cursor: str | None = None

        while True:
            self._rate_bucket.consume()  # DATA-05: rate limit check before every call
            response = self._markets_api.get_markets(
                series_ticker=series_ticker,
                status="open",
                limit=200,
                cursor=cursor,
            )
            markets = response.markets or []
            for market in markets:
                snapshots.append(MarketSnapshot.from_sdk_market(market, captured_at))

            cursor = response.cursor
            if not cursor:
                break

        return snapshots
