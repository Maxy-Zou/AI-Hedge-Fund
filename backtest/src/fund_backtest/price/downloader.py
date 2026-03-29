"""Chunked yfinance downloader with tenacity retry on rate limit.

Public API:
    download_in_chunks(tickers, start, end, batch_size, batch_sleep_secs) -> list[(str, pd.DataFrame)]
    get_failed_tickers(raw_df, requested_tickers) -> list[str]

Internal:
    _download_batch(tickers, **kwargs) -> pd.DataFrame  — tenacity-decorated yf.download call
"""
from __future__ import annotations

import time
from datetime import date

import pandas as pd
import requests
import structlog
import yfinance as yf
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from yfinance.exceptions import YFRateLimitError

log = structlog.get_logger(__name__)


@retry(
    retry=retry_if_exception_type((YFRateLimitError, requests.exceptions.HTTPError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=5, max=60),
    reraise=True,
)
def _download_batch(tickers: list[str], **kwargs) -> pd.DataFrame:
    """Download a single batch of tickers via yfinance with tenacity retry.

    Retries on YFRateLimitError and requests.HTTPError with exponential backoff.
    Max 5 attempts, backoff between 5s and 60s.

    Args:
        tickers: List of ticker symbols to download.
        **kwargs: Passed directly to yf.download (start, end, auto_adjust, etc.)

    Returns:
        MultiIndex DataFrame with (field, ticker) columns.

    Raises:
        YFRateLimitError: After 5 failed attempts.
        requests.exceptions.HTTPError: After 5 failed attempts.
    """
    return yf.download(tickers, **kwargs, progress=False, multi_level_index=True)


def get_failed_tickers(raw_df: pd.DataFrame, requested_tickers: list[str]) -> list[str]:
    """Return tickers with no valid data (missing or all-NaN Close column).

    A ticker is considered failed if:
    1. It is absent from the DataFrame columns entirely, OR
    2. Its Close column is all NaN (no valid price data).

    Args:
        raw_df: MultiIndex DataFrame returned by yf.download.
        requested_tickers: The tickers that were requested in the batch.

    Returns:
        List of tickers that have no usable data.
    """
    failed = []
    if raw_df.empty:
        return list(requested_tickers)
    available = set(raw_df.columns.get_level_values(1))
    for ticker in requested_tickers:
        if ticker not in available:
            failed.append(ticker)
        elif raw_df["Close"][ticker].isna().all():
            failed.append(ticker)
    return failed


def download_in_chunks(
    tickers: list[str],
    start: date,
    end: date | None = None,
    batch_size: int = 80,
    batch_sleep_secs: float = 1.0,
) -> list[tuple[str, pd.DataFrame]]:
    """Download tickers in batches of batch_size with a sleep between batches.

    Splits the ticker list into chunks of at most batch_size and downloads
    each chunk with yfinance. Sleeps batch_sleep_secs between batches (but
    NOT after the last batch) to avoid rate limiting.

    Args:
        tickers: Full list of ticker symbols to download.
        start: Start date for historical data.
        end: End date for historical data (None = today).
        batch_size: Max tickers per yfinance call (default 80).
        batch_sleep_secs: Seconds to sleep between batches (default 1.0).

    Returns:
        List of (ticker, ohlcv_df) tuples for each ticker that had valid data.
        Tickers with all-NaN or missing data are excluded silently
        (log warning emitted).
    """
    results: list[tuple[str, pd.DataFrame]] = []
    batches = [tickers[i : i + batch_size] for i in range(0, len(tickers), batch_size)]

    for idx, batch in enumerate(batches):
        log.info(
            "downloading_batch",
            batch_num=idx + 1,
            total_batches=len(batches),
            size=len(batch),
        )
        raw = _download_batch(batch, start=start, end=end, auto_adjust=True)
        available = set(raw.columns.get_level_values(1)) if not raw.empty else set()

        for ticker in batch:
            if ticker in available and not raw["Close"][ticker].isna().all():
                ticker_df = raw.xs(ticker, level=1, axis=1).dropna(how="all")
                results.append((ticker, ticker_df))

        failed = get_failed_tickers(raw, batch)
        if failed:
            log.warning("tickers_failed_in_batch", failed=failed, count=len(failed))

        # Sleep between batches — but NOT after the last batch
        if idx < len(batches) - 1:
            time.sleep(batch_sleep_secs)

    return results
