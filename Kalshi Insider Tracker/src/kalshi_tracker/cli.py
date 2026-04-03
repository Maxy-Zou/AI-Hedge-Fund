"""CLI entry points for Kalshi Insider Tracker.

Commands:
    start: Start the Kalshi insider tracking daemon.
"""

from __future__ import annotations

import structlog
import typer

from kalshi_tracker.config import load_app_settings, load_kalshi_settings
from kalshi_tracker.daemon.poller import PollingDaemon, make_poll_tick
from kalshi_tracker.daemon.warmup import WarmupTracker
from kalshi_tracker.db.session import create_engine_from_settings, get_session_factory
from kalshi_tracker.kalshi.client import KalshiClient
from kalshi_tracker.logging import configure_logging

app = typer.Typer(name="kalshi-tracker", help="Kalshi Insider Tracker CLI")
logger = structlog.get_logger(__name__)


@app.command()
def start(log_level: str = "INFO") -> None:
    """Start the Kalshi insider tracking polling daemon.

    Polls all politics/policy markets every KALSHI_TRACKER_POLL_INTERVAL_SECONDS
    seconds and persists snapshots to PostgreSQL. Exits cleanly on SIGTERM.
    """
    configure_logging(log_level)
    logger.info("tracker_starting", log_level=log_level)

    app_settings = load_app_settings()
    kalshi_settings = load_kalshi_settings()
    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)
    client = KalshiClient(kalshi_settings)
    warmup = WarmupTracker(threshold=app_settings.warmup_snapshots)
    poll_tick = make_poll_tick(client, session_factory, warmup)
    daemon = PollingDaemon(poll_tick, app_settings.poll_interval_seconds)

    logger.info(
        "polling_daemon_configured",
        poll_interval_seconds=app_settings.poll_interval_seconds,
        warmup_snapshots=app_settings.warmup_snapshots,
    )
    daemon.start()
