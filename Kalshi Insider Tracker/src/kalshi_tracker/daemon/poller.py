"""Polling daemon: APScheduler-based market snapshot collector.

Fetches all politics/policy markets from Kalshi every N seconds,
translates domain snapshots to ORM rows, and persists them to PostgreSQL.
Maintains WarmupTracker state for downstream signal detection (DATA-06).

Architecture:
  PollingDaemon: owns the APScheduler BackgroundScheduler lifecycle
  make_poll_tick: factory returning the job function with injected dependencies
  _to_orm: pure translator from domain dataclass to ORM row (no business logic)

APScheduler version: 3.x (NOT 4.x — incompatible API). Import paths use
  apscheduler.schedulers.background and apscheduler.triggers.interval.
"""

from __future__ import annotations

import signal
import time
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session, sessionmaker

from kalshi_tracker.daemon.warmup import WarmupTracker
from kalshi_tracker.db.models import MarketSnapshot as OrmSnapshot
from kalshi_tracker.kalshi.client import KalshiClient, RateLimitError
from kalshi_tracker.kalshi.types import MarketSnapshot as DomainSnapshot

if TYPE_CHECKING:
    from kalshi_tracker.execution.executor import TradeExecutor
    from kalshi_tracker.signals.engine import SignalEngine

logger = structlog.get_logger(__name__)


def _get_close_times(tickers: list[str], session: Session) -> dict[str, datetime | None]:
    """Fetch close_time for each ticker in one SELECT IN query.

    Args:
        tickers: List of market tickers to look up.
        session: Active SQLAlchemy session.

    Returns:
        Dict mapping ticker -> close_time (None if market not found or has no close_time).
    """
    from kalshi_tracker.db.models import Market

    if not tickers:
        return {}
    rows = session.query(Market).filter(Market.ticker.in_(tickers)).all()
    return {row.ticker: row.close_time for row in rows}


def _to_orm(domain: DomainSnapshot) -> OrmSnapshot:
    """Translate a domain MarketSnapshot dataclass to an ORM row.

    Pure translation — no business logic. raw_snapshot left empty in v1;
    the JSONB field was designed for future audit use (see Phase 1 research Q1).

    Args:
        domain: Frozen domain dataclass from KalshiClient.

    Returns:
        New OrmSnapshot instance (not yet added to any session).
    """
    return OrmSnapshot(
        ticker=domain.ticker,
        series_ticker=domain.series_ticker,
        yes_bid=domain.yes_bid,
        yes_ask=domain.yes_ask,
        no_bid=domain.no_bid,
        no_ask=domain.no_ask,
        last_price=domain.last_price,
        volume=domain.volume,
        volume_24h=domain.volume_24h,
        status=domain.status,
        captured_at=domain.captured_at,
        raw_snapshot={},  # v1: leave empty; no consumer yet (see RESEARCH.md open Q1)
    )


def make_poll_tick(
    client: KalshiClient,
    session_factory: sessionmaker[Session],
    warmup: WarmupTracker,
    signal_engine: SignalEngine | None = None,
    trade_executor: "TradeExecutor | None" = None,
) -> Callable[[], None]:
    """Factory returning the polling job function with injected dependencies.

    Using a factory (not a class method) so the job function is a plain callable
    that APScheduler can schedule without any special serialization.

    Args:
        client: KalshiClient for fetching market data.
        session_factory: SQLAlchemy sessionmaker for DB writes.
        warmup: WarmupTracker to update after each successful tick.
        signal_engine: Optional SignalEngine for signal detection after each tick.
            Pass None (default) to disable signal detection — preserves backwards compat.
        trade_executor: Optional TradeExecutor for executing signals after detection.
            Pass None (default) to disable execution — paper/live controlled by executor.

    Returns:
        poll_tick: Zero-argument callable suitable for APScheduler job.
    """

    def poll_tick() -> None:
        """Single poll tick: fetch markets -> persist snapshots -> update warmup.

        Errors are caught and logged — never re-raised. APScheduler would catch
        unhandled exceptions anyway, but explicit handling gives structured log events.
        """
        tick_start = time.monotonic()

        try:
            snapshots: list[DomainSnapshot] = client.get_politics_markets()
        except RateLimitError:
            logger.warning("poll_tick_rate_limited")
            return
        except Exception:
            logger.warning("poll_tick_api_error", exc_info=True)
            return

        orm_rows = [_to_orm(s) for s in snapshots]

        try:
            with session_factory() as session:
                session.add_all(orm_rows)
                session.commit()  # explicit commit — context manager exit alone does NOT commit
        except Exception:
            logger.warning("poll_tick_db_error", exc_info=True)
            return

        for snap in snapshots:
            warmup.record(snap.ticker)

        if signal_engine is not None:
            # Fetch close_times for all tickers in one query to avoid N+1 queries
            with session_factory() as session:
                close_time_map = _get_close_times(
                    [s.ticker for s in snapshots], session
                )
            for snap in snapshots:
                try:
                    signals = signal_engine.run(
                        snap.ticker,
                        close_time=close_time_map.get(snap.ticker),
                    )
                    if trade_executor is not None:
                        for signal in signals:
                            try:
                                trade_executor.execute(signal)
                            except Exception:
                                logger.warning(
                                    "poll_tick_execution_error",
                                    ticker=snap.ticker,
                                    signal_id=str(signal.id),
                                    exc_info=True,
                                )
                except Exception:
                    logger.warning("poll_tick_signal_error", ticker=snap.ticker, exc_info=True)

        elapsed_ms = int((time.monotonic() - tick_start) * 1000)
        logger.info(
            "poll_tick_complete",
            snapshot_count=len(snapshots),
            elapsed_ms=elapsed_ms,
        )

    return poll_tick


class PollingDaemon:
    """APScheduler-based polling daemon for Kalshi market snapshots.

    Uses BackgroundScheduler (not BlockingScheduler) so the main thread can
    block on signal.pause() and respond to SIGTERM/SIGINT for graceful shutdown.

    Args:
        poll_tick_fn: Zero-argument callable executed every poll_interval_seconds.
        poll_interval_seconds: Interval between polls (1-60s). Default 10.
    """

    def __init__(self, poll_tick_fn: Callable[[], None], poll_interval_seconds: int = 10) -> None:
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(
            poll_tick_fn,
            IntervalTrigger(seconds=poll_interval_seconds),
            id="poll_markets",
            max_instances=1,  # prevent overlap if a tick runs long
            coalesce=True,  # if ticks queued up (e.g. after sleep), run only once
            misfire_grace_time=30,  # allow up to 30s late before skipping
        )
        self._log = logger.bind(poll_interval_seconds=poll_interval_seconds)

    def start(self) -> None:
        """Start the scheduler and block until SIGTERM or KeyboardInterrupt.

        Performs graceful shutdown (waits for running tick to complete) on exit.
        """
        self._scheduler.start()
        self._log.info("polling_daemon_started")
        try:
            signal.pause()  # block main thread; SIGTERM/SIGINT interrupts this
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self._scheduler.shutdown(wait=True)
            self._log.info("polling_daemon_stopped")
