"""Typer CLI for fund-backtest.

Commands:
    fund-backtest universe refresh [--dry-run]
    fund-backtest universe status
"""
from __future__ import annotations

from collections import Counter

import structlog
import typer
from rich.console import Console
from rich.table import Table

from fund_backtest.config import load_app_settings, load_universe_settings
from fund_backtest.db.models import UniverseSnapshot, UniverseTicker
from fund_backtest.db.session import create_engine_from_settings, get_session_factory
from fund_backtest.logging import configure_logging
from fund_backtest.universe.builder import UniverseBuilder

app = typer.Typer(
    name="fund-backtest",
    help="Shared backtesting infrastructure for the AI Hedge Fund.",
    no_args_is_help=True,
)
universe_app = typer.Typer(help="Manage the mid-cap ticker universe.")
app.add_typer(universe_app, name="universe")

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


if __name__ == "__main__":
    app()
