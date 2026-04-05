"""CLI entry point for the Kalshi backtesting engine.

Commands available in Phase 1:
    ingest — pull and store historical Kalshi contract data

Usage:
    kalshi-backtest ingest --help
    kalshi-backtest ingest --lookback-days 365 --dry-run
    kalshi-backtest ingest --series KXBTC --series PRES
"""
from __future__ import annotations

import structlog
import typer
from pydantic import ValidationError
from rich.console import Console

from kalshi_backtest.config import load_settings
from kalshi_backtest.logging import configure_logging

app = typer.Typer(
    name="kalshi-backtest",
    help="Kalshi prediction market backtesting engine",
    no_args_is_help=True,
)
_console = Console()
logger = structlog.get_logger(__name__)


@app.command()
def ingest(
    lookback_days: int = typer.Option(
        365,
        "--lookback-days",
        help="Days of history to ingest (default: 365)",
    ),
    series: list[str] = typer.Option(  # noqa: B008
        [],
        "--series",
        help="Series tickers to filter (e.g. --series KXBTC --series PRES). Default: all.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print intended ingestion plan without writing to the database.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Log level: DEBUG, INFO, WARNING",
    ),
) -> None:
    """Ingest historical Kalshi contract data into the local DuckDB store.

    Loads credentials from environment variables (or .env file):
        KALSHI_BACKTEST_API_KEY_ID
        KALSHI_BACKTEST_PRIVATE_KEY_PATH
        KALSHI_BACKTEST_DB_PATH (optional, default: kalshi_backtest.duckdb)

    Run with --dry-run to preview the ingestion plan without API calls.
    """
    configure_logging(log_level)

    # Load config — fail fast with a clear message if credentials missing
    try:
        settings = load_settings()
    except ValidationError as exc:
        _console.print("[red]Configuration error:[/red] Missing required environment variables.")
        for err in exc.errors():
            field = " -> ".join(str(f) for f in err["loc"])
            _console.print(f"  * [yellow]{field}[/yellow]: {err['msg']}")
        _console.print("\nSee .env.example for required variables.")
        raise typer.Exit(code=1) from exc

    series_list = list(series) if series else None
    end_note = f"last {lookback_days} days"
    series_note = f", series: {', '.join(series_list)}" if series_list else ", all series"

    if dry_run:
        _console.print("[bold]Dry-run mode — no data will be written.[/bold]")
        _console.print(f"  Ingestion window: {end_note}{series_note}")
        _console.print(f"  Database path:    {settings.db_path}")
        _console.print(f"  API base URL:     {settings.api_base_url}")
        _console.print(f"  Rate limit:       {settings.rate_limit_rpm} RPM")
        raise typer.Exit(code=0)

    # Build component graph
    import httpx

    from kalshi_backtest.db.repository import MarketRepository
    from kalshi_backtest.db.schema import get_or_create_db
    from kalshi_backtest.ingestion.client import (
        KalshiClientRouter,
        KalshiHistoricalClient,
        KalshiLiveClient,
    )
    from kalshi_backtest.ingestion.cutoff import HistoricalCutoffResolver
    from kalshi_backtest.ingestion.fetcher import CandlestickFetcher, MarketFetcher
    from kalshi_backtest.ingestion.pipeline import IngestionPipeline
    from kalshi_backtest.ingestion.validator import DataValidator

    con = get_or_create_db(settings.db_path)
    repo = MarketRepository(con)

    live_client = KalshiLiveClient(settings)
    hist_client = KalshiHistoricalClient(settings)
    http_client = httpx.Client(timeout=30.0)

    cutoff_resolver = HistoricalCutoffResolver(
        http_client=http_client,
        auth_headers=hist_client._auth_headers,
    )
    router = KalshiClientRouter(live_client, hist_client, cutoff_resolver)
    market_fetcher = MarketFetcher(hist_client)
    candle_fetcher = CandlestickFetcher(router)
    pipeline = IngestionPipeline(market_fetcher, candle_fetcher, repo)

    _console.print(f"[bold]Starting ingestion:[/bold] {end_note}{series_note}")

    result = pipeline.run(
        lookback_days=lookback_days,
        series_tickers=series_list,
    )

    # Post-ingestion validation report
    if result.markets_upserted > 0:
        all_tickers = [m["ticker"] for m in repo.get_markets()]
        validator = DataValidator(con)
        validator.validate_all(all_tickers[:100])  # cap at 100 to avoid slow report

    _console.print(
        f"\n[green]Ingestion complete.[/green] "
        f"Markets: {result.markets_upserted}, "
        f"Candles: {result.candles_inserted}, "
        f"Failures: {len(result.markets_failed)}, "
        f"Duration: {result.duration_seconds:.1f}s"
    )

    if result.markets_failed:
        _console.print(f"[yellow]Failed tickers:[/yellow] {', '.join(result.markets_failed[:10])}")
        con.close()
        http_client.close()
        raise typer.Exit(code=1)

    con.close()
    http_client.close()
