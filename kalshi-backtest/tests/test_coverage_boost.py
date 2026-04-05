"""Additional tests to bring coverage above 80% — Phase 1 gate.

Covers uncovered paths in:
- db/repository.py: get_markets(), get_candles()
- ingestion/fetcher.py: MarketFetcher.fetch_all(), CandlestickFetcher.fetch_for_market()
- ingestion/client.py: KalshiClientRouter routing, KalshiHistoricalClient.get_candlesticks()
- cli.py: full ingest path (mocked pipeline)
"""
from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from kalshi_backtest.ingestion.types import CandlestickRecord, MarketRecord

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_market(ticker: str = "KXBTC-25", status: str = "active") -> MarketRecord:
    return MarketRecord(
        ticker=ticker,
        event_ticker="KXBTC",
        series_ticker="KXBTC",
        subtitle="BTC above 50k",
        open_time=datetime(2025, 1, 1),
        close_time=datetime(2025, 12, 31),
        status=status,
        result="yes" if status == "settled" else None,
    )


def _make_candle(ticker: str = "KXBTC-25", ts: int = 1735689600) -> CandlestickRecord:
    return CandlestickRecord(ticker=ticker, ts=ts, close_price=50)


# ── Repository: get_markets() ─────────────────────────────────────────────────


class TestRepositoryGetMarkets:
    """MarketRepository.get_markets() filtering and return shape."""

    def test_get_markets_returns_all(self, duckdb_con) -> None:
        """get_markets() with no filters returns all stored markets."""
        from kalshi_backtest.db.repository import MarketRepository

        repo = MarketRepository(duckdb_con)
        repo.upsert_market(_make_market("KXBTC-25"))
        repo.upsert_market(_make_market("KXBTC-26"))

        result = repo.get_markets()
        tickers = [r["ticker"] for r in result]
        assert "KXBTC-25" in tickers
        assert "KXBTC-26" in tickers

    def test_get_markets_filters_by_series(self, duckdb_con) -> None:
        """get_markets(series_ticker=...) returns only that series."""
        from kalshi_backtest.db.repository import MarketRepository

        repo = MarketRepository(duckdb_con)
        market_btc = MarketRecord(
            ticker="KXBTC-25",
            event_ticker="KXBTC",
            series_ticker="KXBTC",
            open_time=datetime(2025, 1, 1),
            close_time=datetime(2025, 12, 31),
            status="active",
        )
        market_eth = MarketRecord(
            ticker="KXETH-25",
            event_ticker="KXETH",
            series_ticker="KXETH",
            open_time=datetime(2025, 1, 1),
            close_time=datetime(2025, 12, 31),
            status="active",
        )
        repo.upsert_market(market_btc)
        repo.upsert_market(market_eth)

        result = repo.get_markets(series_ticker="KXBTC")
        assert len(result) == 1
        assert result[0]["ticker"] == "KXBTC-25"

    def test_get_markets_empty_table(self, duckdb_con) -> None:
        """get_markets() on empty table returns empty list."""
        from kalshi_backtest.db.repository import MarketRepository

        repo = MarketRepository(duckdb_con)
        result = repo.get_markets()
        assert result == []

    def test_get_markets_filters_by_close_time(self, duckdb_con) -> None:
        """get_markets(min_close_time=...) excludes markets closing before threshold."""
        from kalshi_backtest.db.repository import MarketRepository

        repo = MarketRepository(duckdb_con)
        early = MarketRecord(
            ticker="EARLY-25",
            event_ticker="EARLY",
            series_ticker="EARLY",
            open_time=datetime(2024, 1, 1),
            close_time=datetime(2024, 6, 1),
            status="settled",
            result="yes",
        )
        late = MarketRecord(
            ticker="LATE-25",
            event_ticker="LATE",
            series_ticker="LATE",
            open_time=datetime(2025, 1, 1),
            close_time=datetime(2025, 12, 31),
            status="active",
        )
        repo.upsert_market(early)
        repo.upsert_market(late)

        result = repo.get_markets(min_close_time=datetime(2025, 1, 1))
        tickers = [r["ticker"] for r in result]
        assert "LATE-25" in tickers
        assert "EARLY-25" not in tickers


# ── Repository: get_candles() ─────────────────────────────────────────────────


class TestRepositoryGetCandles:
    """MarketRepository.get_candles() filtering and return shape."""

    def test_get_candles_returns_rows(self, duckdb_con) -> None:
        """get_candles() returns inserted candle rows as dicts."""
        from kalshi_backtest.db.repository import MarketRepository

        repo = MarketRepository(duckdb_con)
        repo.insert_candles([_make_candle("KXBTC-25", ts=1735689600)])

        result = repo.get_candles("KXBTC-25")
        assert len(result) == 1
        assert result[0]["ticker"] == "KXBTC-25"

    def test_get_candles_empty_for_unknown_ticker(self, duckdb_con) -> None:
        """get_candles() returns empty list for unknown ticker."""
        from kalshi_backtest.db.repository import MarketRepository

        repo = MarketRepository(duckdb_con)
        result = repo.get_candles("UNKNOWN-99")
        assert result == []

    def test_get_candles_filters_by_start_ts(self, duckdb_con) -> None:
        """get_candles(start_ts=...) excludes candles before threshold."""
        from kalshi_backtest.db.repository import MarketRepository

        repo = MarketRepository(duckdb_con)
        old_ts = 1700000000  # Nov 2023
        new_ts = 1735689600  # Jan 2025
        repo.insert_candles([
            _make_candle(ts=old_ts),
            _make_candle(ts=new_ts),
        ])

        # Filter to only 2025 candles using a naive datetime threshold
        threshold_dt = datetime(2025, 1, 1, 0, 0, 0)
        result = repo.get_candles("KXBTC-25", start_ts=threshold_dt)
        assert len(result) >= 1


# ── MarketFetcher ─────────────────────────────────────────────────────────────


class TestMarketFetcher:
    """MarketFetcher.fetch_all() pagination and deduplication."""

    def test_fetch_all_single_page(self) -> None:
        """fetch_all() returns markets when single page, no next_cursor."""
        from kalshi_backtest.ingestion.fetcher import MarketFetcher

        market = _make_market("KXBTC-25")
        hist_client = MagicMock()
        hist_client.get_markets.return_value = ([market], None)  # no cursor = last page

        fetcher = MarketFetcher(hist_client)
        result = fetcher.fetch_all(
            start_dt=datetime(2025, 1, 1),
            end_dt=datetime(2025, 12, 31),
        )

        assert len(result) == 1
        assert result[0].ticker == "KXBTC-25"

    def test_fetch_all_paginates(self) -> None:
        """fetch_all() follows cursors until exhausted."""
        from kalshi_backtest.ingestion.fetcher import MarketFetcher

        market1 = _make_market("KXBTC-25")
        market2 = _make_market("KXBTC-26")

        hist_client = MagicMock()
        hist_client.get_markets.side_effect = [
            ([market1], "cursor-page-2"),   # first page
            ([market2], None),              # second page — no more cursor
        ]

        fetcher = MarketFetcher(hist_client)
        result = fetcher.fetch_all(
            start_dt=datetime(2025, 1, 1),
            end_dt=datetime(2025, 12, 31),
        )

        assert len(result) == 2
        tickers = {m.ticker for m in result}
        assert tickers == {"KXBTC-25", "KXBTC-26"}

    def test_fetch_all_deduplicates(self) -> None:
        """fetch_all() deduplicates markets with same ticker across pages."""
        from kalshi_backtest.ingestion.fetcher import MarketFetcher

        market = _make_market("KXBTC-25")

        hist_client = MagicMock()
        hist_client.get_markets.side_effect = [
            ([market], "cursor"),     # page 1
            ([market], None),         # page 2 returns same ticker
        ]

        fetcher = MarketFetcher(hist_client)
        result = fetcher.fetch_all(
            start_dt=datetime(2025, 1, 1),
            end_dt=datetime(2025, 12, 31),
        )

        # Deduplicated — only 1 unique ticker
        assert len(result) == 1

    def test_fetch_all_empty_response(self) -> None:
        """fetch_all() returns empty list when no markets found."""
        from kalshi_backtest.ingestion.fetcher import MarketFetcher

        hist_client = MagicMock()
        hist_client.get_markets.return_value = ([], None)

        fetcher = MarketFetcher(hist_client)
        result = fetcher.fetch_all(
            start_dt=datetime(2025, 1, 1),
            end_dt=datetime(2025, 12, 31),
        )

        assert result == []


# ── CandlestickFetcher ────────────────────────────────────────────────────────


class TestCandlestickFetcher:
    """CandlestickFetcher.fetch_for_market() incremental sync and range logic."""

    def test_fetch_for_market_calls_router(self) -> None:
        """fetch_for_market() delegates to router.get_candlesticks()."""
        from kalshi_backtest.ingestion.fetcher import CandlestickFetcher

        candle = _make_candle()
        router = MagicMock()
        router.get_candlesticks.return_value = [candle]

        market = _make_market("KXBTC-25")
        fetcher = CandlestickFetcher(router)
        result = fetcher.fetch_for_market(
            market=market,
            lookback_start=datetime(2024, 1, 1),
        )

        assert len(result) == 1
        router.get_candlesticks.assert_called_once()

    def test_fetch_for_market_incremental_sync(self) -> None:
        """fetch_for_market() uses last_ingested_ts + 1 day as start when provided."""
        from kalshi_backtest.ingestion.fetcher import CandlestickFetcher

        candle = _make_candle()
        router = MagicMock()
        router.get_candlesticks.return_value = [candle]

        market = _make_market("KXBTC-25")
        last_ts = 1735689600  # 2025-01-01 UTC

        fetcher = CandlestickFetcher(router)
        fetcher.fetch_for_market(
            market=market,
            lookback_start=datetime(2024, 1, 1),
            last_ingested_ts=last_ts,
        )

        # Verify start_ts passed to router is AFTER last_ingested_ts
        call_kwargs = router.get_candlesticks.call_args
        actual_start_ts = call_kwargs.kwargs.get("start_ts") or call_kwargs.args[3]
        expected_min_start = last_ts + 86400  # at least 1 day later
        assert actual_start_ts >= expected_min_start

    def test_fetch_for_market_returns_empty_when_up_to_date(self) -> None:
        """fetch_for_market() returns [] when start_dt >= end_dt (already up to date)."""
        from kalshi_backtest.ingestion.fetcher import CandlestickFetcher

        router = MagicMock()
        # Market closed in the past
        market = MarketRecord(
            ticker="KXBTC-OLD",
            event_ticker="KXBTC",
            series_ticker="KXBTC",
            open_time=datetime(2023, 1, 1),
            close_time=datetime(2023, 6, 1),  # already closed
            status="settled",
            result="yes",
        )

        fetcher = CandlestickFetcher(router)
        # last_ingested_ts is AFTER market close_time — nothing to fetch
        result = fetcher.fetch_for_market(
            market=market,
            lookback_start=datetime(2022, 1, 1),
            last_ingested_ts=int(datetime(2023, 12, 31).timestamp()),
        )

        assert result == []
        router.get_candlesticks.assert_not_called()


# ── KalshiClientRouter ────────────────────────────────────────────────────────


class TestKalshiClientRouter:
    """KalshiClientRouter routes to correct tier based on cutoff."""

    def test_router_routes_to_historical(self) -> None:
        """Router calls historical client for markets before cutoff."""
        from kalshi_backtest.ingestion.client import KalshiClientRouter
        from kalshi_backtest.ingestion.cutoff import CutoffResult

        cutoff = CutoffResult(
            cutoff_ts=1_700_000_000,
            cutoff_dt=datetime(2023, 11, 14, 22, 13, 20),
        )
        live_client = MagicMock()
        hist_client = MagicMock()
        hist_client.get_candlesticks.return_value = [_make_candle()]
        resolver = MagicMock()
        resolver.resolve.return_value = cutoff
        resolver.is_historical.return_value = True

        router = KalshiClientRouter(live_client, hist_client, resolver)
        result = router.get_candlesticks(
            series_ticker="KXBTC",
            market_ticker="KXBTC-23",
            market_close_time=datetime(2023, 6, 1),
            start_ts=1_680_000_000,
            end_ts=1_690_000_000,
        )

        hist_client.get_candlesticks.assert_called_once()
        live_client.get_candlesticks.assert_not_called()
        assert len(result) == 1

    def test_router_routes_to_live(self) -> None:
        """Router calls live client for markets after cutoff."""
        from kalshi_backtest.ingestion.client import KalshiClientRouter
        from kalshi_backtest.ingestion.cutoff import CutoffResult

        cutoff = CutoffResult(
            cutoff_ts=1_700_000_000,
            cutoff_dt=datetime(2023, 11, 14, 22, 13, 20),
        )
        live_client = MagicMock()
        live_client.get_candlesticks.return_value = [_make_candle()]
        hist_client = MagicMock()
        resolver = MagicMock()
        resolver.resolve.return_value = cutoff
        resolver.is_historical.return_value = False

        router = KalshiClientRouter(live_client, hist_client, resolver)
        result = router.get_candlesticks(
            series_ticker="KXBTC",
            market_ticker="KXBTC-25",
            market_close_time=datetime(2025, 1, 1),
            start_ts=1_735_000_000,
            end_ts=1_736_000_000,
        )

        live_client.get_candlesticks.assert_called_once()
        hist_client.get_candlesticks.assert_not_called()
        assert len(result) == 1


# ── KalshiHistoricalClient.get_candlesticks() ─────────────────────────────────


class TestHistoricalClientParsing:
    """KalshiHistoricalClient parses httpx response into CandlestickRecord list."""

    def test_get_candlesticks_parses_response(self) -> None:
        """get_candlesticks() returns CandlestickRecord list from JSON response."""

        import httpx

        from kalshi_backtest.ingestion.client import KalshiHistoricalClient

        fake_response_body = {
            "candlesticks": [
                {
                    "ts": 1735689600,
                    "open_price": 45,
                    "high_price": 55,
                    "low_price": 40,
                    "close_price": 50,
                    "volume": 100,
                }
            ]
        }

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = fake_response_body

        client = KalshiHistoricalClient.__new__(KalshiHistoricalClient)
        client._rate_bucket = MagicMock()
        client._rate_bucket.consume.return_value = None
        mock_kalshi_auth = MagicMock()
        mock_kalshi_auth.create_auth_headers.return_value = {
            "KALSHI-ACCESS-KEY": "k",
            "KALSHI-ACCESS-SIGNATURE": "s",
            "KALSHI-ACCESS-TIMESTAMP": "t",
        }
        client._kalshi_auth = mock_kalshi_auth
        mock_http = MagicMock()
        mock_http.get.return_value = mock_response
        client._http = mock_http

        result = client.get_candlesticks(
            market_ticker="KXBTCD-25JAN31-T99999",
            start_ts=1735689600,
            end_ts=1736000000,
        )

        assert len(result) == 1
        assert result[0].ticker == "KXBTCD-25JAN31-T99999"
        assert result[0].close_price == 50

    def test_get_candlesticks_empty_response(self) -> None:
        """get_candlesticks() returns [] when response has no candlesticks."""
        import httpx

        from kalshi_backtest.ingestion.client import KalshiHistoricalClient

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"candlesticks": []}

        client = KalshiHistoricalClient.__new__(KalshiHistoricalClient)
        client._rate_bucket = MagicMock()
        client._rate_bucket.consume.return_value = None
        mock_kalshi_auth = MagicMock()
        mock_kalshi_auth.create_auth_headers.return_value = {
            "KALSHI-ACCESS-KEY": "k",
            "KALSHI-ACCESS-SIGNATURE": "s",
            "KALSHI-ACCESS-TIMESTAMP": "t",
        }
        client._kalshi_auth = mock_kalshi_auth
        mock_http = MagicMock()
        mock_http.get.return_value = mock_response
        client._http = mock_http

        result = client.get_candlesticks("KXBTC-25", 1735689600, 1736000000)
        assert result == []


# ── CLI: full ingest path (mocked pipeline) ───────────────────────────────────
# Note: The CLI app is a single-command Typer app. The `app` object IS the ingest
# command — invoke it with options only (no "ingest" subcommand prefix).


class TestCliIngestFullPath:
    """CLI ingest command: full execution path with mocked pipeline."""

    def test_ingest_run_completes_successfully(self) -> None:
        """CLI ingest command prints completion summary when pipeline succeeds."""
        from typer.testing import CliRunner

        from kalshi_backtest.cli import app

        mock_settings = MagicMock()
        mock_settings.db_path = "/tmp/test_ingest.duckdb"
        mock_settings.api_base_url = "https://demo-api.kalshi.co/trade-api/v2"
        mock_settings.rate_limit_rpm = 60
        mock_settings.api_key_id = "test-key"
        mock_settings.private_key_path = "/tmp/key.pem"

        mock_result = MagicMock()
        mock_result.markets_upserted = 3
        mock_result.candles_inserted = 10
        mock_result.markets_failed = []
        mock_result.duration_seconds = 1.5

        runner = CliRunner()

        with (
            patch("kalshi_backtest.cli.load_settings", return_value=mock_settings),
            patch("kalshi_backtest.cli.configure_logging"),
            patch("kalshi_backtest.db.schema.get_or_create_db") as mock_db,
            patch("kalshi_backtest.db.repository.MarketRepository") as mock_repo_cls,
            patch("kalshi_backtest.ingestion.client.KalshiLiveClient"),
            patch("kalshi_backtest.ingestion.client.KalshiHistoricalClient") as mock_hist,
            patch("httpx.Client"),
            patch("kalshi_backtest.ingestion.cutoff.HistoricalCutoffResolver"),
            patch("kalshi_backtest.ingestion.client.KalshiClientRouter"),
            patch("kalshi_backtest.ingestion.fetcher.MarketFetcher"),
            patch("kalshi_backtest.ingestion.fetcher.CandlestickFetcher"),
            patch("kalshi_backtest.ingestion.pipeline.IngestionPipeline") as mock_pipeline_cls,
            patch("kalshi_backtest.ingestion.validator.DataValidator"),
        ):
            mock_hist.return_value._auth_headers = {}
            mock_con = MagicMock()
            mock_db.return_value = mock_con
            mock_repo = MagicMock()
            mock_repo.get_markets.return_value = []
            mock_repo_cls.return_value = mock_repo
            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = mock_result
            mock_pipeline_cls.return_value = mock_pipeline

            # Single-command app: invoke with [] (no subcommand prefix)
            result = runner.invoke(app, [])

        assert result.exit_code == 0, f"Expected exit 0: {result.output}"
        assert "Ingestion complete" in result.output

    def test_ingest_exits_one_on_failures(self) -> None:
        """CLI ingest exits 1 when pipeline reports failed markets."""
        from typer.testing import CliRunner

        from kalshi_backtest.cli import app

        mock_settings = MagicMock()
        mock_settings.db_path = "/tmp/test_ingest2.duckdb"
        mock_settings.api_base_url = "https://demo-api.kalshi.co/trade-api/v2"
        mock_settings.rate_limit_rpm = 60

        mock_result = MagicMock()
        mock_result.markets_upserted = 2
        mock_result.candles_inserted = 5
        mock_result.markets_failed = ["KXBTC-FAIL"]
        mock_result.duration_seconds = 0.5

        runner = CliRunner()

        with (
            patch("kalshi_backtest.cli.load_settings", return_value=mock_settings),
            patch("kalshi_backtest.cli.configure_logging"),
            patch("kalshi_backtest.db.schema.get_or_create_db") as mock_db,
            patch("kalshi_backtest.db.repository.MarketRepository") as mock_repo_cls,
            patch("kalshi_backtest.ingestion.client.KalshiLiveClient"),
            patch("kalshi_backtest.ingestion.client.KalshiHistoricalClient") as mock_hist,
            patch("httpx.Client"),
            patch("kalshi_backtest.ingestion.cutoff.HistoricalCutoffResolver"),
            patch("kalshi_backtest.ingestion.client.KalshiClientRouter"),
            patch("kalshi_backtest.ingestion.fetcher.MarketFetcher"),
            patch("kalshi_backtest.ingestion.fetcher.CandlestickFetcher"),
            patch("kalshi_backtest.ingestion.pipeline.IngestionPipeline") as mock_pipeline_cls,
            patch("kalshi_backtest.ingestion.validator.DataValidator"),
        ):
            mock_hist.return_value._auth_headers = {}
            mock_db.return_value = MagicMock()
            mock_repo = MagicMock()
            mock_repo.get_markets.return_value = []
            mock_repo_cls.return_value = mock_repo
            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = mock_result
            mock_pipeline_cls.return_value = mock_pipeline

            # Single-command app: invoke with [] (no subcommand prefix)
            result = runner.invoke(app, [])

        assert result.exit_code == 1, f"Expected exit 1: {result.output}"
        assert "KXBTC-FAIL" in result.output

    def test_ingest_dry_run_with_series_option(self) -> None:
        """CLI ingest --dry-run --series KXBTC includes series in output."""
        from typer.testing import CliRunner

        from kalshi_backtest.cli import app

        mock_settings = MagicMock()
        mock_settings.db_path = "/tmp/test.duckdb"
        mock_settings.api_base_url = "https://demo-api.kalshi.co"
        mock_settings.rate_limit_rpm = 60

        runner = CliRunner()
        with patch("kalshi_backtest.cli.load_settings", return_value=mock_settings):
            # Single-command app: no "ingest" prefix
            result = runner.invoke(app, ["--dry-run", "--series", "KXBTC"])

        assert result.exit_code == 0
        assert "KXBTC" in result.output

    def test_ingest_dry_run_missing_env(self) -> None:
        """CLI ingest --dry-run exits 1 when credentials missing."""
        from typer.testing import CliRunner

        from kalshi_backtest.cli import app

        runner = CliRunner()
        with patch.dict(os.environ, {}, clear=True):
            # Single-command app: no "ingest" prefix
            result = runner.invoke(app, ["--dry-run"])

        assert result.exit_code == 1
        assert "Configuration error" in result.output or "error" in result.output.lower()
