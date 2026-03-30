"""Typer CLI for fund-backtest.

Commands:
    fund-backtest universe refresh [--dry-run]
    fund-backtest universe status
    fund-backtest data download [--dry-run]
    fund-backtest data update
    fund-backtest data coverage
    fund-backtest backtest run --signal ai-washing
    fund-backtest backtest export [--tearsheet] [--csv] [--json] [--all] [--output-dir DIR]
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd
import structlog
import typer
from rich.console import Console
from rich.table import Table

from fund_backtest.config import load_app_settings, load_cost_config, load_price_settings, load_universe_settings
from fund_backtest.dashboard.demo_data import make_demo_bundle, make_demo_result
from fund_backtest.db.models import PriceAnomalyORM, UniverseSnapshot, UniverseTicker
from fund_backtest.db.session import create_engine_from_settings, get_session_factory
from fund_backtest.logging import configure_logging
from fund_backtest.metrics.engine import MetricsEngine
from fund_backtest.price.builder import PriceBuilder
from fund_backtest.price.repository import PriceBarRepository
from fund_backtest.reports import ExportBuilder, TearsheetBuilder
from fund_backtest.signal.adapter import SignalAdapter
from fund_backtest.signal.loaders import AiWashingLoader, SignalLoadError
from fund_backtest.simulator.engine import PortfolioSimulator
from fund_backtest.universe.builder import UniverseBuilder

app = typer.Typer(
    name="fund-backtest",
    help="Shared backtesting infrastructure for the AI Hedge Fund.",
    no_args_is_help=True,
)
universe_app = typer.Typer(help="Manage the mid-cap ticker universe.")
app.add_typer(universe_app, name="universe")

data_app = typer.Typer(help="Manage OHLCV price data.")
app.add_typer(data_app, name="data")

backtest_app = typer.Typer(help="Backtest run and export commands.")
app.add_typer(backtest_app, name="backtest")

console = Console()
log = structlog.get_logger(__name__)


@universe_app.command()
def refresh(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview changes without writing to DB.",
    ),
) -> None:
    """Refresh the mid-cap universe: seed S&P 400, validate market caps, update sector data.

    Fetches the Wikipedia S&P 400 table, validates market caps via yfinance,
    and upserts results into PostgreSQL. Historical snapshots are preserved.
    Tickers that exit the $2B-$10B range are marked inactive (never deleted).
    """
    universe_settings = load_universe_settings()

    if dry_run:
        console.print("[yellow]dry-run mode — no database writes will occur[/yellow]")
        console.print(f"Would refresh universe using: {universe_settings.seed_url}")
        console.print(
            f"Market cap range: "
            f"${universe_settings.market_cap_min_cents / 100:,.0f} – "
            f"${universe_settings.market_cap_max_cents / 100:,.0f}"
        )
        return

    settings = load_app_settings()
    configure_logging(settings.log_level)

    try:
        engine = create_engine_from_settings(settings)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            builder = UniverseBuilder(session=session, settings=universe_settings)
            result = builder.refresh()

        table = Table(title="Universe Refresh Complete", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Snapshot date", result.snapshot_date)
        table.add_row("Active tickers", str(result.active_count))
        table.add_row("New tickers", str(result.new_count))
        table.add_row("Removed tickers", str(result.removed_count))
        console.print(table)

    except Exception as exc:
        console.print(f"[red]Error during refresh: {exc}[/red]")
        log.exception("refresh_failed", error=str(exc))
        raise typer.Exit(code=1) from exc


@universe_app.command()
def status() -> None:
    """Display current universe size and sector breakdown."""
    settings = load_app_settings()
    configure_logging(settings.log_level)

    try:
        engine = create_engine_from_settings(settings)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            active_tickers = (
                session.query(UniverseTicker).filter_by(is_active=True).all()
            )
            latest_snapshot = (
                session.query(UniverseSnapshot)
                .order_by(UniverseSnapshot.snapshot_date.desc())
                .first()
            )

        if not active_tickers:
            console.print(
                "[yellow]Universe is empty. Run `fund-backtest universe refresh` first.[/yellow]"
            )
            return

        # Summary table
        summary = Table(title="Universe Status", show_header=True)
        summary.add_column("Property", style="cyan")
        summary.add_column("Value", style="green")
        summary.add_row("Active tickers", str(len(active_tickers)))
        if latest_snapshot:
            summary.add_row("Last refreshed", str(latest_snapshot.snapshot_date))
        console.print(summary)

        # Sector breakdown table
        sector_counts = Counter(t.gics_sector for t in active_tickers if t.gics_sector)
        sector_table = Table(title="Sector Breakdown", show_header=True)
        sector_table.add_column("GICS Sector", style="cyan")
        sector_table.add_column("Count", style="green", justify="right")
        for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
            sector_table.add_row(sector, str(count))
        console.print(sector_table)

    except Exception as exc:
        console.print(f"[red]Error fetching status: {exc}[/red]")
        log.exception("status_failed", error=str(exc))
        raise typer.Exit(code=1) from exc


@data_app.command()
def download(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview download plan without writing to DB.",
    ),
) -> None:
    """Download 5 years of daily OHLCV bars for all active universe tickers."""
    _price_yaml = Path(__file__).parent.parent.parent / "config" / "price.yaml"
    price_settings = load_price_settings(config_path=_price_yaml if _price_yaml.exists() else None)
    if dry_run:
        console.print("[yellow]dry-run mode — no database writes will occur[/yellow]")
        console.print(
            f"batch_size={price_settings.batch_size},"
            f" lookback_years={price_settings.lookback_years}"
        )

    settings = load_app_settings()
    configure_logging(settings.log_level)

    try:
        engine = create_engine_from_settings(settings)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            builder = PriceBuilder(session=session, settings=price_settings)
            summary = builder.download(dry_run=dry_run)

        if not dry_run:
            table = Table(title="Download Complete", show_header=True)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Tickers requested", str(summary.requested))
            table.add_row("Tickers successful", str(len(summary.successful)))
            table.add_row("Tickers failed", str(len(summary.failed)))
            table.add_row("Bars inserted", str(summary.bars_inserted))
            console.print(table)

    except Exception as exc:
        console.print(f"[red]Error during download: {exc}[/red]")
        log.exception("download_failed", error=str(exc))
        raise typer.Exit(code=1) from exc


@data_app.command()
def update() -> None:
    """Append new bars since last download. Historical data is never modified."""
    settings = load_app_settings()
    configure_logging(settings.log_level)

    try:
        engine = create_engine_from_settings(settings)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            _price_yaml = Path(__file__).parent.parent.parent / "config" / "price.yaml"
            builder = PriceBuilder(
                session=session,
                settings=load_price_settings(config_path=_price_yaml if _price_yaml.exists() else None),
            )
            summary = builder.update()

        table = Table(title="Incremental Update Complete", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Tickers requested", str(summary.requested))
        table.add_row("Tickers successful", str(len(summary.successful)))
        table.add_row("Tickers failed", str(len(summary.failed)))
        table.add_row("Bars inserted", str(summary.bars_inserted))
        console.print(table)

    except Exception as exc:
        console.print(f"[red]Error during update: {exc}[/red]")
        log.exception("update_failed", error=str(exc))
        raise typer.Exit(code=1) from exc


@data_app.command()
def coverage() -> None:
    """Show data coverage: tickers with bars, date range, unreviewed anomaly count."""
    settings = load_app_settings()
    configure_logging(settings.log_level)

    try:
        engine = create_engine_from_settings(settings)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            from sqlalchemy import text as sa_text

            repo = PriceBarRepository(session)
            tickers_with_bars = repo.get_coverage_tickers()
            result = session.execute(
                sa_text(
                    "SELECT MIN(bar_date) AS min_date, MAX(bar_date) AS max_date"
                    " FROM price_bars"
                )
            ).first()
            anomaly_count = (
                session.query(PriceAnomalyORM).filter_by(is_reviewed=False).count()
            )

        table = Table(title="Price Data Coverage", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Tickers with bars", str(len(tickers_with_bars)))
        if result and result.min_date:
            table.add_row("Earliest bar date", str(result.min_date))
            table.add_row("Latest bar date", str(result.max_date))
        else:
            table.add_row("Date range", "No data")
        table.add_row("Unreviewed anomalies", str(anomaly_count))
        console.print(table)

    except Exception as exc:
        console.print(f"[red]Error fetching coverage: {exc}[/red]")
        log.exception("coverage_failed", error=str(exc))
        raise typer.Exit(code=1) from exc


@backtest_app.command(name="run")
def run(
    signal: str = typer.Option(..., "--signal", help="Signal source (e.g. 'ai-washing')"),
    output_dir: Path = typer.Option(Path("."), "--output-dir", help="Output directory for exports"),
    export_all: bool = typer.Option(False, "--export-all", help="Generate all exports after run"),
) -> None:
    """Run full end-to-end backtest from signal load through metrics computation.

    Loads signal data from the configured source, adapts scores to portfolio weights,
    runs the portfolio simulator, and computes risk metrics. Exits 1 on any pipeline failure.
    """
    # Validate signal name early — before loading settings (avoids DB config requirement)
    if signal != "ai-washing":
        console.print(f"[red]Unknown signal source: '{signal}'. Supported: 'ai-washing'[/red]")
        raise typer.Exit(code=1)

    settings = load_app_settings()
    configure_logging(settings.log_level)
    _log = structlog.get_logger(__name__)

    try:
        engine = create_engine_from_settings(settings)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            # Stage 1: Load signal
            loader = AiWashingLoader(session)
            signal_frame = loader.load()
            _log.info("signal_loaded", n_dates=len(signal_frame), n_tickers=len(signal_frame.columns))

            # Stage 2: Load price data for signal tickers and date range
            repo = PriceBarRepository(session)
            tickers = list(signal_frame.columns)
            start = signal_frame.index.min().date()
            end = signal_frame.index.max().date()
            bars = repo.get_bars(tickers=tickers, start_date=start, end_date=end)
            records = [
                {"date": b.bar_date, "ticker": b.ticker, "close": b.close_cents / 100}
                for b in bars
            ]
            price_df = pd.DataFrame(records)
            price_frame = price_df.pivot_table(index="date", columns="ticker", values="close")
            price_frame.index = pd.DatetimeIndex(pd.to_datetime(price_frame.index))
            price_frame.columns.name = None

            # Stage 3: Adapt signal to weights
            weight_frame = SignalAdapter().adapt(signal_frame)

            # Stage 4: Simulate portfolio
            portfolio_result = PortfolioSimulator().simulate(weight_frame, price_frame)
            _log.info("simulation_complete", n_trading_days=len(portfolio_result.net_returns))

            # Stage 5: Compute risk metrics
            bundle = MetricsEngine().compute(portfolio_result)
            _log.info("metrics_complete", sharpe=bundle.sharpe, cagr=bundle.cagr)

        # Stage 6 (optional): Export
        if export_all:
            output_dir.mkdir(parents=True, exist_ok=True)
            cost_cfg = load_cost_config()
            ExportBuilder().export_csv(portfolio_result, cost_cfg, output_dir)
            ExportBuilder().export_json(bundle, cost_cfg, output_dir)
            console.print(f"[green]Exports written to {output_dir}[/green]")

        console.print(
            f"[green]Pipeline complete — Sharpe: {bundle.sharpe:.2f}, CAGR: {bundle.cagr:.2%}[/green]"
        )

    except SignalLoadError as exc:
        console.print(f"[red]Signal unavailable: {exc}[/red]")
        _log.error("signal_load_failed", error=str(exc))
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Pipeline error: {exc}[/red]")
        _log.exception("pipeline_failed", error=str(exc))
        raise typer.Exit(code=1) from exc


@backtest_app.command(name="export")
def export(
    tearsheet: bool = typer.Option(False, "--tearsheet", help="Generate PDF tearsheet"),
    csv: bool = typer.Option(False, "--csv", help="Export CSV files (daily_returns, positions, trade_log)"),
    json_export: bool = typer.Option(False, "--json", help="Export metrics JSON"),
    all_exports: bool = typer.Option(False, "--all", help="Run all exports"),
    output_dir: Path = typer.Option(Path("."), "--output-dir", help="Output directory"),
) -> None:
    """Export backtest results using demo data (Phase 7). Live data wired in Phase 8."""
    _log = structlog.get_logger(__name__)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = make_demo_result()
    bundle = make_demo_bundle(result)
    cost_config = load_cost_config()

    do_tearsheet = tearsheet or all_exports
    do_csv = csv or all_exports
    do_json = json_export or all_exports

    if not any([do_tearsheet, do_csv, do_json]):
        typer.echo("No export type specified. Use --tearsheet, --csv, --json, or --all.")
        raise typer.Exit(code=1)

    if do_tearsheet:
        path = TearsheetBuilder().build(result, bundle, cost_config, output_dir / "tearsheet.pdf")
        _log.info("tearsheet_exported", path=str(path))
        typer.echo(f"Tearsheet: {path}")

    if do_csv:
        paths = ExportBuilder().export_csv(result, cost_config, output_dir)
        for p in paths:
            _log.info("csv_exported", path=str(p))
            typer.echo(f"CSV: {p}")

    if do_json:
        path = ExportBuilder().export_json(bundle, cost_config, output_dir)
        _log.info("json_exported", path=str(path))
        typer.echo(f"JSON: {path}")


if __name__ == "__main__":
    app()
