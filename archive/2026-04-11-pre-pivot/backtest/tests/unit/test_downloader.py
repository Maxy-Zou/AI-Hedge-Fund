"""Unit tests for price/downloader.py — chunking, retry, and failed ticker detection.

Tests are written TDD-first (RED phase). They validate:
- Chunking logic splits tickers into correct batch sizes
- download_in_chunks returns per-ticker DataFrames
- get_failed_tickers detects both missing columns and all-NaN Close
- tenacity retry fires on YFRateLimitError
- time.sleep is called between batches (not after last)
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest
from yfinance.exceptions import YFRateLimitError

from fund_backtest.price.downloader import (
    _download_batch,
    download_in_chunks,
    get_failed_tickers,
)


def _make_multi_index_df(tickers: list[str], close_values: dict[str, list[float | None]]) -> pd.DataFrame:
    """Build a MultiIndex DataFrame mimicking yfinance multi-ticker output.

    Creates a DataFrame with MultiIndex columns (field, ticker) where each
    ticker has OHLCV columns. close_values maps ticker -> list of close prices.
    None values become NaN.
    """
    dates = pd.date_range("2024-01-01", periods=3, freq="B")
    fields = ["Open", "High", "Low", "Close", "Volume"]
    tuples = [(field, ticker) for field in fields for ticker in tickers]
    columns = pd.MultiIndex.from_tuples(tuples)
    data = {}
    for field in fields:
        for ticker in tickers:
            if field == "Close":
                vals = close_values.get(ticker, [100.0, 101.0, 102.0])
                data[(field, ticker)] = [float("nan") if v is None else v for v in vals]
            elif field == "Volume":
                data[(field, ticker)] = [1_000_000, 1_100_000, 900_000]
            else:
                data[(field, ticker)] = [100.0, 101.0, 102.0]
    return pd.DataFrame(data, index=dates, columns=pd.MultiIndex.from_tuples(data.keys()))


class TestChunkTickers:
    """Tests for internal chunking logic in download_in_chunks."""

    def test_chunk_tickers_into_batches(self) -> None:
        """200 tickers with batch_size=80 should produce 3 batches: [80, 80, 40]."""
        tickers = [f"T{i:03d}" for i in range(200)]
        # Access the internal chunking via download_in_chunks behavior:
        # Patch _download_batch to capture call arguments
        raw_df = _make_multi_index_df(["T000"], {"T000": [100.0, 101.0, 102.0]})

        call_args_list = []

        def fake_download(batch: list[str], **kwargs) -> pd.DataFrame:
            call_args_list.append(len(batch))
            return _make_multi_index_df(batch[:1], {batch[0]: [100.0, 101.0, 102.0]})

        with patch("fund_backtest.price.downloader._download_batch", side_effect=fake_download):
            with patch("time.sleep"):
                download_in_chunks(
                    tickers,
                    start=date(2024, 1, 1),
                    end=date(2024, 12, 31),
                    batch_size=80,
                )

        assert call_args_list == [80, 80, 40], f"Expected [80, 80, 40] but got {call_args_list}"


class TestDownloadInChunks:
    """Tests for download_in_chunks() public function."""

    def test_download_in_chunks_returns_per_ticker_dataframes(self) -> None:
        """Mock yf.download to return valid MultiIndex DataFrame; assert 2 (ticker, df) tuples."""
        tickers = ["AAPL", "MSFT"]
        raw_df = _make_multi_index_df(tickers, {"AAPL": [150.0, 151.0, 152.0], "MSFT": [300.0, 301.0, 302.0]})

        with patch("yfinance.download", return_value=raw_df):
            with patch("time.sleep"):
                results = download_in_chunks(
                    tickers,
                    start=date(2024, 1, 1),
                    end=date(2024, 12, 31),
                    batch_size=10,
                )

        assert len(results) == 2
        result_tickers = [t for t, _ in results]
        assert "AAPL" in result_tickers
        assert "MSFT" in result_tickers
        for ticker, df in results:
            assert isinstance(df, pd.DataFrame)
            assert "Close" in df.columns

    def test_download_in_chunks_sleeps_between_batches(self) -> None:
        """With batch_size=1 and 2 tickers, sleep should be called once (between batches, not after last)."""
        tickers = ["AAPL", "MSFT"]

        def fake_download(batch: list[str], **kwargs) -> pd.DataFrame:
            return _make_multi_index_df(batch, {t: [100.0, 101.0, 102.0] for t in batch})

        with patch("yfinance.download", side_effect=fake_download):
            with patch("time.sleep") as mock_sleep:
                download_in_chunks(
                    tickers,
                    start=date(2024, 1, 1),
                    end=date(2024, 12, 31),
                    batch_size=1,
                )

        assert mock_sleep.call_count == 1, (
            f"Expected sleep called exactly once (between batches), got {mock_sleep.call_count}"
        )


class TestGetFailedTickers:
    """Tests for get_failed_tickers() helper."""

    def test_get_failed_tickers_all_nan_close(self) -> None:
        """Ticker with all-NaN Close column should be returned as failed."""
        raw_df = _make_multi_index_df(
            ["AAPL", "FAKE"],
            {"AAPL": [150.0, 151.0, 152.0], "FAKE": [None, None, None]},
        )
        failed = get_failed_tickers(raw_df, ["AAPL", "FAKE"])
        assert "FAKE" in failed
        assert "AAPL" not in failed

    def test_get_failed_tickers_missing_from_columns(self) -> None:
        """Ticker absent from DataFrame columns should be in the failed list."""
        raw_df = _make_multi_index_df(["AAPL"], {"AAPL": [150.0, 151.0, 152.0]})
        failed = get_failed_tickers(raw_df, ["AAPL", "MSFT"])
        assert "MSFT" in failed
        assert "AAPL" not in failed

    def test_get_failed_tickers_empty_df_returns_all(self) -> None:
        """Empty DataFrame should mark all requested tickers as failed."""
        empty_df = pd.DataFrame()
        failed = get_failed_tickers(empty_df, ["AAPL", "MSFT"])
        assert sorted(failed) == ["AAPL", "MSFT"]


class TestDownloadBatchRetry:
    """Tests for _download_batch() tenacity retry behavior."""

    def test_download_batch_retries_on_rate_limit(self) -> None:
        """Mock yf.download to raise YFRateLimitError twice then return valid data.

        Assert that _download_batch() succeeds on the third call and that
        yf.download was invoked 3 times total (confirming retry occurred).

        The retry wait is patched to 0 so the test runs instantly.
        """
        import fund_backtest.price.downloader as dl_mod

        tickers = ["AAPL"]
        valid_df = _make_multi_index_df(tickers, {"AAPL": [150.0, 151.0, 152.0]})

        call_count = {"n": 0}

        def counting_flaky(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise YFRateLimitError()
            return valid_df

        import yfinance as yf

        with patch.object(yf, "download", side_effect=counting_flaky):
            # Override tenacity wait to 0 to avoid sleeping in tests
            original_wait = dl_mod._download_batch.retry.wait
            dl_mod._download_batch.retry.wait = lambda retry_state: 0
            try:
                result = dl_mod._download_batch(tickers, start=date(2024, 1, 1))
            finally:
                dl_mod._download_batch.retry.wait = original_wait

        assert call_count["n"] == 3, (
            f"Expected 3 calls (2 YFRateLimitError + 1 success), got {call_count['n']}"
        )
        assert result is valid_df
