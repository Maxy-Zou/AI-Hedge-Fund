"""CLI entry points for Kalshi Insider Tracker.

Commands:
    start: Start the Kalshi insider tracking daemon.
    dashboard: Launch the live monitoring dashboard in a browser.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import structlog
import typer
from rich import print as rprint
from rich.console import Console

from kalshi_tracker.config import load_app_settings, load_execution_settings, load_kalshi_settings
from kalshi_tracker.daemon.poller import PollingDaemon, make_poll_tick
from kalshi_tracker.daemon.warmup import WarmupTracker
from kalshi_tracker.db.session import create_engine_from_settings, get_session_factory
from kalshi_tracker.execution.executor import TradeExecutor
from kalshi_tracker.execution.risk_guard import RiskGuard
from kalshi_tracker.kalshi.client import KalshiClient
from kalshi_tracker.logging import configure_logging

app = typer.Typer(name="kalshi-tracker", help="Kalshi Insider Tracker CLI")
logger = structlog.get_logger(__name__)
console = Console()


@app.command()
def start(
    log_level: str = "INFO",
    live: bool = typer.Option(False, "--live", help="Enable live trade execution (default: paper mode)"),
) -> None:
    """Start the Kalshi insider tracking polling daemon.

    Polls all politics/policy markets every KALSHI_TRACKER_POLL_INTERVAL_SECONDS
    seconds and persists snapshots to PostgreSQL. Exits cleanly on SIGTERM.

    By default runs in paper mode — signals are detected and logged but no real
    orders are placed. Pass --live to enable actual order placement on Kalshi.
    """
    configure_logging(log_level)
    logger.info("tracker_starting", log_level=log_level, live_mode=live)

    app_settings = load_app_settings()
    kalshi_settings = load_kalshi_settings()
    exec_settings = load_execution_settings()

    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)
    client = KalshiClient(kalshi_settings)
    warmup = WarmupTracker(threshold=app_settings.warmup_snapshots)

    # Construct RiskGuard (always needed — enforces hard limits in both modes)
    risk_guard = RiskGuard(session_factory=session_factory)

    # Paper mode by default; live mode requires explicit --live flag
    portfolio_api = None
    if live:
        # Reuse the authenticated PortfolioApi from KalshiClient — no duplicate RSA setup
        portfolio_api = client.portfolio_api
        rprint("[yellow]Live mode enabled — real orders will be placed on Kalshi[/yellow]")
    else:
        rprint("[green]Paper mode (default) — signals detected but no real orders[/green]")

    trade_executor = TradeExecutor(
        session_factory=session_factory,
        risk_guard=risk_guard,
        portfolio_api=portfolio_api,
        confidence_threshold=exec_settings.confidence_threshold,
    )

    poll_tick = make_poll_tick(
        client=client,
        session_factory=session_factory,
        warmup=warmup,
        signal_engine=None,
        trade_executor=trade_executor,
    )
    daemon = PollingDaemon(poll_tick, app_settings.poll_interval_seconds)

    logger.info(
        "polling_daemon_configured",
        poll_interval_seconds=app_settings.poll_interval_seconds,
        warmup_snapshots=app_settings.warmup_snapshots,
        live_mode=live,
        confidence_threshold=exec_settings.confidence_threshold,
    )
    daemon.start()


@app.command()
def dashboard(
    port: int = typer.Option(8501, help="Port for the Streamlit server"),
    host: str = typer.Option("localhost", help="Host for the Streamlit server"),
) -> None:
    """Launch the live monitoring dashboard in a browser."""
    app_path = Path(__file__).parent / "dashboard" / "app.py"
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(app_path),
        "--server.port", str(port),
        "--server.address", host,
    ]
    console.print(f"[green]Starting dashboard on http://{host}:{port}[/green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    subprocess.run(cmd, check=False)
