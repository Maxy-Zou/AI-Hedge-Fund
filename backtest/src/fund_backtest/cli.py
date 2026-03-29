"""Typer CLI for fund-backtest.

Commands:
    fund-backtest universe refresh [--dry-run]
    fund-backtest universe status
    fund-backtest data download [--dry-run]
    fund-backtest data update
    fund-backtest data coverage
"""
from __future__ import annotations

from collections import Counter

import structlog
import typer
from rich.console import Console
from rich.table import Table

from fund_backtest.config import load_app_settings, load_price_settings, load_universe_settings
from fund_backtest.db.models import PriceAnomalyORM, UniverseSnapshot, UniverseTicker
from fund_backtest.db.session import create_engine_from_settings, get_session_factory
from fund_backtest.logging import configure_logging
from fund_backtest.price.builder import PriceBuilder
from fund_backtest.price.repository import PriceBarRepository
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
    price_settings = load_price_settings()
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
            builder = PriceBuilder(session=session, settings=load_price_settings())
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


if __name__ == "__main__":
    app()
