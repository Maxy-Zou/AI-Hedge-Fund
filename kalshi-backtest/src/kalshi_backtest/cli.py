"""CLI entry point for the Kalshi backtesting engine.

Commands available:
    ingest  — pull and store historical Kalshi contract data
    run     — execute a backtest against stored historical data
    compare — run two stub strategies side-by-side and print a comparison table

Usage:
    kalshi-backtest ingest --help
    kalshi-backtest ingest --lookback-days 365 --dry-run
    kalshi-backtest ingest --series KXBTC --series PRES
    kalshi-backtest run --lookback-days 90
    kalshi-backtest run --dry-run
    kalshi-backtest compare --dry-run
    kalshi-backtest compare --lookback-days 180
"""
from __future__ import annotations

from datetime import UTC
from pathlib import Path

import structlog
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from kalshi_backtest.config import load_settings
from kalshi_backtest.logging import configure_logging

app = typer.Typer(
    name="kalshi-backtest",
    help="Kalshi prediction market backtesting engine",
    no_args_is_help=True,
)
_console = Console()
logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Metric display helpers
# ---------------------------------------------------------------------------

_SCALAR_ROWS = [
    ("Total Return %", lambda m: f"{m.total_return_pct:.2f}%"),
    ("CAGR %", lambda m: f"{m.cagr_pct:.2f}%"),
    ("Sharpe", lambda m: f"{m.sharpe:.3f}"),
    ("Sortino", lambda m: f"{m.sortino:.3f}"),
    ("Max Drawdown %", lambda m: f"{m.max_drawdown_pct:.2f}%"),
    ("Win Rate %", lambda m: f"{m.win_rate_pct:.2f}%"),
    ("Profit Factor", lambda m: f"{m.profit_factor:.3f}"),
    ("Total Trades", lambda m: str(m.total_trades)),
    ("Settled Markets", lambda m: str(m.settled_markets)),
]


def print_metrics_summary(metrics, console: Console) -> None:  # type: ignore[type-arg]
    """Print a two-column Metric / Value table for a single BacktestMetrics object.

    Args:
        metrics: BacktestMetrics instance to display.
        console: Rich Console to print to.
    """
    table = Table(title="Backtest Metrics", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", justify="right")

    for label, fmt in _SCALAR_ROWS:
        table.add_row(label, fmt(metrics))

    console.print(table)

    if metrics.sample_size_warning:
        console.print(
            f"[bold yellow]Warning: N={metrics.settled_markets} settled markets "
            "— results may be statistically unreliable (N<30)[/bold yellow]"
        )


def print_comparison_table(results: list, console: Console) -> None:  # type: ignore[type-arg]
    """Print a multi-column strategy comparison table.

    Displays one column per strategy with all scalar metrics as rows.

    Args:
        results: List of BacktestMetrics instances (one per strategy).
        console: Rich Console to print to.
    """
    table = Table(title="Strategy Comparison", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", no_wrap=True)
    for m in results:
        table.add_column(m.strategy_name, justify="right")

    for label, fmt in _SCALAR_ROWS:
        row = [label] + [fmt(m) for m in results]
        table.add_row(*row)

    console.print(table)

    if any(m.sample_size_warning for m in results):
        console.print(
            "[bold yellow]Warning: one or more strategies have N<30 settled markets "
            "— results may be statistically unreliable[/bold yellow]"
        )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


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


@app.command()
def run(
    lookback_days: int = typer.Option(
        365,
        "--lookback-days",
        help="Days of history to replay (default: 365)",
    ),
    series: list[str] = typer.Option(  # noqa: B008
        [],
        "--series",
        help="Series tickers to filter (e.g. --series KXBTC). Default: all.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print intended backtest plan without executing.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Log level: DEBUG, INFO, WARNING",
    ),
    output_dir: Path | None = typer.Option(  # noqa: B008
        None,
        "--output-dir",
        help="Write trade_log.csv and dashboard.html to this directory.",
    ),
) -> None:
    """Run a backtest against historical Kalshi contract data.

    Uses a naive pass-through stub strategy for demonstration.
    Replace with a real Strategy implementation to evaluate signal quality.

    Loads credentials from environment variables (or .env file):
        KALSHI_BACKTEST_API_KEY_ID
        KALSHI_BACKTEST_PRIVATE_KEY_PATH
        KALSHI_BACKTEST_DB_PATH (optional, default: kalshi_backtest.duckdb)

    Run with --dry-run to preview the backtest window without executing.
    """
    configure_logging(log_level)

    from datetime import datetime, timedelta

    end_date = datetime.now(tz=UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=lookback_days)
    series_list = list(series) if series else None

    if dry_run:
        _console.print("[bold]Dry-run mode — no simulation will be executed.[/bold]")
        _console.print(
            f"  Backtest window: last {lookback_days} days"
            f" ({start_date.date()} to {end_date.date()})"
        )
        if series_list:
            _console.print(f"  Series filter:   {', '.join(series_list)}")
        raise typer.Exit(code=0)

    # Credentials required for live execution — fail fast with a clear message
    try:
        settings = load_settings()
    except ValidationError as exc:
        _console.print("[red]Configuration error:[/red] Missing required environment variables.")
        for err in exc.errors():
            field = " -> ".join(str(f) for f in err["loc"])
            _console.print(f"  * [yellow]{field}[/yellow]: {err['msg']}")
        _console.print("\nSee .env.example for required variables.")
        raise typer.Exit(code=1) from exc

    # Lazy imports — only load heavy deps when actually running
    from kalshi_backtest.db.repository import MarketRepository
    from kalshi_backtest.db.schema import get_or_create_db
    from kalshi_backtest.metrics import DashboardBuilder, MetricsCalculator, export_trade_log
    from kalshi_backtest.simulation.fill_engine import FillEngine
    from kalshi_backtest.simulation.runner import BacktestRunner

    con = get_or_create_db(settings.db_path)
    repo = MarketRepository(con)
    fill_engine = FillEngine(spread_floor=1)
    runner_obj = BacktestRunner(repo=repo, fill_engine=fill_engine)

    # Stub strategy — always passes (no signals generated). Replace in Phase 4.
    class _PassThroughStrategy:
        def generate_signals(self, snapshot, open_positions):  # type: ignore[override]
            return []

    strategy = _PassThroughStrategy()
    _console.print(f"[bold]Starting backtest:[/bold] last {lookback_days} days")

    result = runner_obj.run(
        strategy=strategy,
        start_date=start_date,
        end_date=end_date,
        series_tickers=series_list,
    )

    # Compute and display metrics
    metrics = MetricsCalculator().compute(result)
    print_metrics_summary(metrics, _console)

    _console.print(
        f"\n[green]Backtest complete.[/green] "
        f"Settled contracts: {result.settled_contracts}, "
        f"Total P&L: {result.total_pnl_cents / 100:.2f} USD, "
        f"Total fees: {result.total_fees_cents / 100:.2f} USD, "
        f"Trades: {len(result.trade_log)}"
    )

    # Write output files if --output-dir is given
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        export_trade_log(result, output_dir / "trade_log.csv")
        DashboardBuilder(metrics, result.trade_log).write_html(output_dir / "dashboard.html")
        _console.print(f"[green]Reports written to:[/green] {output_dir}")

    con.close()


@app.command()
def compare(
    lookback_days: int = typer.Option(
        365,
        "--lookback-days",
        help="Days of history to replay for each strategy (default: 365)",
    ),
    series: list[str] = typer.Option(  # noqa: B008
        [],
        "--series",
        help="Series tickers to filter. Default: all.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print comparison table with zero-valued metrics — no DB or credentials needed.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Log level: DEBUG, INFO, WARNING",
    ),
    output_dir: Path | None = typer.Option(  # noqa: B008
        None,
        "--output-dir",
        help="Write per-strategy HTML dashboards to this directory.",
    ),
) -> None:
    """Run two stub strategies side-by-side and print a Rich comparison table.

    In dry-run mode, prints the comparison table with zero-valued metrics for
    StrategyA and StrategyB without loading credentials or accessing the database.

    Loads credentials from environment variables (or .env file) when not using --dry-run:
        KALSHI_BACKTEST_API_KEY_ID
        KALSHI_BACKTEST_PRIVATE_KEY_PATH
        KALSHI_BACKTEST_DB_PATH (optional, default: kalshi_backtest.duckdb)
    """
    configure_logging(log_level)

    from kalshi_backtest.metrics import BacktestMetrics

    if dry_run:
        # Return zero-valued metrics for both strategies without DB access
        metrics_a = BacktestMetrics(strategy_name="StrategyA")
        metrics_b = BacktestMetrics(strategy_name="StrategyB")
        print_comparison_table([metrics_a, metrics_b], _console)
        raise typer.Exit(code=0)

    # Credentials required for live execution
    try:
        settings = load_settings()
    except ValidationError as exc:
        _console.print("[red]Configuration error:[/red] Missing required environment variables.")
        for err in exc.errors():
            field = " -> ".join(str(f) for f in err["loc"])
            _console.print(f"  * [yellow]{field}[/yellow]: {err['msg']}")
        _console.print("\nSee .env.example for required variables.")
        raise typer.Exit(code=1) from exc

    from datetime import datetime, timedelta

    from kalshi_backtest.db.repository import MarketRepository
    from kalshi_backtest.db.schema import get_or_create_db
    from kalshi_backtest.metrics import DashboardBuilder, MetricsCalculator
    from kalshi_backtest.simulation.fill_engine import FillEngine
    from kalshi_backtest.simulation.runner import BacktestRunner

    end_date = datetime.now(tz=UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=lookback_days)
    series_list = list(series) if series else None

    con = get_or_create_db(settings.db_path)
    repo = MarketRepository(con)
    fill_engine = FillEngine(spread_floor=1)

    class _PassThroughStrategy:
        def __init__(self, name: str) -> None:
            self._name = name

        @property
        def name(self) -> str:
            return self._name

        def generate_signals(self, snapshot, open_positions):  # type: ignore[override]
            return []

    strategy_a = _PassThroughStrategy("StrategyA")
    strategy_b = _PassThroughStrategy("StrategyB")

    all_metrics = []
    for strat in (strategy_a, strategy_b):
        runner_obj = BacktestRunner(repo=repo, fill_engine=fill_engine)
        _console.print(f"[bold]Running {strat.name}...[/bold]")
        result = runner_obj.run(
            strategy=strat,
            start_date=start_date,
            end_date=end_date,
            series_tickers=series_list,
        )
        metrics = MetricsCalculator().compute(result)
        # Override strategy_name from the strat object (stub result may not carry it)
        metrics = metrics.model_copy(update={"strategy_name": strat.name})
        all_metrics.append((strat.name, metrics, result))

    print_comparison_table([m for _, m, _ in all_metrics], _console)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for strat_name, metrics, result in all_metrics:
            DashboardBuilder(metrics, result.trade_log).write_html(
                output_dir / f"dashboard_{strat_name}.html"
            )
        _console.print(f"[green]Dashboards written to:[/green] {output_dir}")

    con.close()
