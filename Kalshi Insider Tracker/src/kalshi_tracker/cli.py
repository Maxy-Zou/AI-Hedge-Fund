"""CLI entry points for Kalshi Insider Tracker.

Commands:
    start: Start the Kalshi insider tracking daemon (full implementation in Phase 2+).
"""

from __future__ import annotations

import structlog
import typer

from kalshi_tracker.logging import configure_logging

app = typer.Typer(name="kalshi-tracker", help="Kalshi Insider Tracker CLI")
logger = structlog.get_logger(__name__)


@app.command()
def start(log_level: str = "INFO") -> None:
    """Start the Kalshi insider tracking daemon."""
    configure_logging(log_level)
    logger.info("tracker_starting", log_level=log_level)
    typer.echo("Starting Kalshi Tracker...")
