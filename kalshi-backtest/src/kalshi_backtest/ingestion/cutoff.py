"""Resolves the Kalshi live/historical API tier boundary at runtime.

Kalshi partitions data at a rolling cutoff timestamp. Markets settled
before this cutoff are ONLY queryable via /historical/* endpoints.
Live endpoints return empty results (not 404) for pre-cutoff data.

Critical: Never hardcode the cutoff date — it advances forward over time.
Always call GET /historical/cutoff to discover the current boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


logger = structlog.get_logger(__name__)

_HISTORICAL_CUTOFF_URL = "https://api.elections.kalshi.com/trade-api/v2/historical/cutoff"


@dataclass(frozen=True)
class CutoffResult:
    """Result of a cutoff resolution call.

    Attributes:
        cutoff_ts: Unix epoch of the live/historical boundary.
        cutoff_dt: Same value as naive UTC datetime.
    """

    cutoff_ts: int
    cutoff_dt: datetime


class HistoricalCutoffResolver:
    """Calls GET /historical/cutoff to determine the current tier boundary.

    Args:
        http_client: httpx.Client to use for the request. Injected for testability.
        auth_headers: Dict of auth headers for the Kalshi API.
    """

    def __init__(
        self,
        http_client: httpx.Client,
        auth_headers: dict[str, str],
    ) -> None:
        self._http = http_client
        self._auth_headers = auth_headers
        self._cached: CutoffResult | None = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
    )
    def resolve(self, *, force_refresh: bool = False) -> CutoffResult:
        """Fetch and cache the current historical cutoff timestamp.

        Results are cached in-process to avoid redundant API calls.
        Pass force_refresh=True to bypass the cache (e.g. long-running processes).

        Args:
            force_refresh: If True, ignore cached value and re-fetch.

        Returns:
            CutoffResult with cutoff_ts (Unix epoch) and cutoff_dt (naive UTC).

        Raises:
            httpx.HTTPStatusError: If the API returns a non-2xx response after retries.
        """
        if self._cached is not None and not force_refresh:
            return self._cached

        resp = self._http.get(_HISTORICAL_CUTOFF_URL, headers=self._auth_headers)
        resp.raise_for_status()

        data = resp.json()
        cutoff_ts = int(data["cutoff_ts"])
        cutoff_dt = datetime.utcfromtimestamp(cutoff_ts)  # naive UTC

        result = CutoffResult(cutoff_ts=cutoff_ts, cutoff_dt=cutoff_dt)
        self._cached = result
        logger.info("cutoff_resolved", cutoff_ts=cutoff_ts, cutoff_dt=str(cutoff_dt))
        return result

    def is_historical(self, market_close_time: datetime, cutoff: CutoffResult) -> bool:
        """Return True if a market's close_time is before the cutoff (historical tier).

        Args:
            market_close_time: Market's close_time as naive UTC datetime.
            cutoff: CutoffResult from resolve().

        Returns:
            True if market should be fetched from historical tier.
        """
        return market_close_time < cutoff.cutoff_dt
