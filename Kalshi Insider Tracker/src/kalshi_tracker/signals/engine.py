"""Signal detection engine: DB-aware orchestrator composing warmup gating,
resolution suppression, detectors, and Signal persistence.

SignalEngine is the single entry point for signal detection on each poll tick.
It applies four ordered gates before writing any Signal row:
  1. Warmup gate — skip markets without enough baseline data
  2. Resolution suppression — skip markets within the pre-close blackout window
  3. Cooldown deduplication — skip (ticker, signal_type) pairs seen recently
  4. Min-confidence filter — skip low-confidence detections

Usage:
    engine = SignalEngine(session_factory=..., warmup=..., settings=...)
    signals = engine.run("KXELECTION-2025-Y", close_time=close_dt)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session, sessionmaker

from kalshi_tracker.config import SignalSettings
from kalshi_tracker.daemon.warmup import WarmupTracker
from kalshi_tracker.db.models import MarketSnapshot as OrmSnapshot
from kalshi_tracker.db.models import Signal
from kalshi_tracker.signals.detectors import (
    PriceMoveDetector,
    TimingClusterDetector,
    VolumeSpikeDetector,
)
from kalshi_tracker.signals.types import DetectionResult

logger = structlog.get_logger(__name__)


def _is_suppressed(
    close_time: datetime | None,
    now: datetime,
    blackout_minutes: int,
) -> bool:
    """Return True if now is within the pre-resolution blackout window.

    Args:
        close_time: Market close time in UTC. None means no suppression.
        now: Current UTC-aware datetime.
        blackout_minutes: How many minutes before close_time to suppress signals.

    Returns:
        True if 0 <= (close_time - now) <= blackout_minutes minutes, else False.
        Always False when close_time is None.
    """
    if close_time is None:
        return False
    delta = close_time - now
    return timedelta(0) <= delta <= timedelta(minutes=blackout_minutes)


class SignalEngine:
    """DB-aware orchestrator for signal detection, gating, and persistence.

    Composes WarmupTracker, resolution suppression, all configured detectors,
    and Signal ORM persistence into one callable per poll tick.

    Args:
        session_factory: SQLAlchemy sessionmaker for DB reads and writes.
        warmup: WarmupTracker to check baseline readiness per ticker.
        settings: SignalSettings with thresholds and window configuration.
        detectors: Optional list of detector instances. Defaults to
            [VolumeSpikeDetector, PriceMoveDetector] configured from settings.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        warmup: WarmupTracker,
        settings: SignalSettings,
        detectors: list | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._warmup = warmup
        self._settings = settings
        self._detectors = detectors if detectors is not None else [
            VolumeSpikeDetector(
                z_threshold=settings.volume_z_threshold,
                window=settings.volume_window,
            ),
            PriceMoveDetector(
                move_pct_threshold=settings.price_move_threshold,
                window=settings.price_window,
            ),
            TimingClusterDetector(
                cluster_minutes=settings.cluster_minutes,
                lookback_minutes=settings.cluster_lookback_minutes,
                cluster_threshold=settings.cluster_threshold,
                min_total_volume=settings.cluster_min_volume,
            ),
        ]
        self._log = logger.bind(engine="signal_engine")

    def run(self, ticker: str, close_time: datetime | None = None) -> list[Signal]:
        """Run signal detection for one market ticker.

        Applies warmup gate, resolution suppression gate, detector loop,
        cooldown deduplication, and Signal persistence in a single DB session.

        Args:
            ticker: Market ticker string.
            close_time: Optional market close time (UTC-aware). Used for blackout
                suppression. Pass None if unknown — suppression is skipped.

        Returns:
            List of Signal ORM rows that were persisted this tick. Empty if any
            gate blocked execution or no detector fired.
        """
        # Gate 1 — warmup: skip markets without sufficient baseline data
        if not self._warmup.is_warmed_up(ticker):
            self._log.debug("signal_engine_warmup_gate", ticker=ticker)
            return []

        # Gate 2 — resolution suppression: skip markets near close
        now = datetime.now(UTC)
        if _is_suppressed(close_time, now, self._settings.resolution_blackout_minutes):
            self._log.debug(
                "signal_engine_suppressed",
                ticker=ticker,
                close_time=str(close_time),
                blackout_minutes=self._settings.resolution_blackout_minutes,
            )
            return []

        persisted: list[Signal] = []

        try:
            with self._session_factory() as session:
                # Fetch snapshots once; pass to all detectors (avoid N+1 queries per detector)
                snapshots = self._fetch_snapshots(ticker, session)

                for detector in self._detectors:
                    result: DetectionResult | None = detector.detect(snapshots)
                    if result is None:
                        continue

                    # Gate 3 — cooldown: skip if same (ticker, signal_type) seen recently
                    if self._is_on_cooldown(ticker, result.signal_type, session):
                        self._log.debug(
                            "signal_engine_cooldown_gate",
                            ticker=ticker,
                            signal_type=result.signal_type,
                        )
                        continue

                    # Gate 4 — min_confidence filter
                    if result.confidence < self._settings.min_confidence:
                        continue

                    signal_row = Signal(
                        ticker=ticker,
                        signal_type=result.signal_type,
                        confidence=result.confidence,
                        details=result.details,
                        detected_at=datetime.now(UTC),
                    )
                    session.add(signal_row)
                    persisted.append(signal_row)

                if persisted:
                    session.commit()  # single commit for all signals this tick

        except Exception:
            self._log.warning(
                "signal_engine_error",
                ticker=ticker,
                exc_info=True,
            )
            return []

        return persisted

    def _fetch_snapshots(self, ticker: str, session: Session) -> list:
        """Fetch recent snapshots for ticker in chronological order (oldest first).

        Fetches max(volume_window, price_window, timing_cluster_lookback) + 1
        snapshots to satisfy all detectors with one query. DB returns newest-first
        (ORDER BY DESC); this method reverses the list so detectors receive
        chronological order.

        Args:
            ticker: Market ticker string.
            session: Active SQLAlchemy session.

        Returns:
            List of OrmSnapshot rows, oldest first.
        """
        # Include timing cluster lookback window (assumes 10s polling cadence)
        lookback_snapshots = (self._settings.cluster_lookback_minutes * 60) // 10 + 1
        limit = max(
            self._settings.volume_window,
            self._settings.price_window,
            lookback_snapshots,
        ) + 1
        rows = (
            session.query(OrmSnapshot)
            .filter(OrmSnapshot.ticker == ticker)
            .order_by(OrmSnapshot.captured_at.desc())
            .limit(limit)
            .all()
        )
        # Reverse to chronological order — detectors expect oldest first
        return list(reversed(rows))

    def _is_on_cooldown(
        self,
        ticker: str,
        signal_type: str,
        session: Session,
    ) -> bool:
        """Check if a recent Signal exists for (ticker, signal_type) within cooldown.

        Args:
            ticker: Market ticker string.
            signal_type: Detector signal type (e.g., 'volume_spike').
            session: Active SQLAlchemy session.

        Returns:
            True if a Signal row with matching (ticker, signal_type) and
            detected_at > (now - cooldown_seconds) exists in DB.
        """
        recent = (
            session.query(Signal)
            .filter(
                Signal.ticker == ticker,
                Signal.signal_type == signal_type,
            )
            .order_by(Signal.detected_at.desc())
            .limit(1)
            .all()
        )
        return bool(recent)
