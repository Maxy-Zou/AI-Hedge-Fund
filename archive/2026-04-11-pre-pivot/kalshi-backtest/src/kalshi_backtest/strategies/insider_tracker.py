"""InsiderTrackerAdapter — reads signals from the Insider Tracker PostgreSQL database.

Implements the Strategy Protocol via SQLAlchemy text() queries against the
Insider Tracker's `signals` table. This module has zero imports from the
`kalshi_tracker` package — it reads directly from the database using raw SQL.

The adapter is look-ahead safe: it only queries signals with
``detected_at < snapshot.ts`` (strictly less-than), ensuring no future
information leaks into the backtest.

Usage:
    from kalshi_backtest.strategies.insider_tracker import InsiderTrackerAdapter

    adapter = InsiderTrackerAdapter(
        db_url="postgresql://user:pass@localhost/kalshi_tracker",
        min_confidence=0.6,
        lookback_hours=24,
    )
    signals = adapter.generate_signals(snapshot, open_positions)
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from kalshi_backtest.simulation.protocol import Signal

if TYPE_CHECKING:
    from kalshi_backtest.simulation.protocol import Position
    from kalshi_backtest.simulation.snapshot import MarketSnapshot

logger = structlog.get_logger(__name__)

_SIGNAL_QUERY = text(
    """
    SELECT signal_type, confidence, details
    FROM signals
    WHERE ticker = :ticker
      AND detected_at >= :start
      AND detected_at < :end
      AND confidence >= :min_conf
    ORDER BY detected_at DESC
    LIMIT 1
    """
)


class InsiderTrackerAdapter:
    """Strategy adapter that sources signals from the Insider Tracker database.

    Queries the Insider Tracker's ``signals`` table for the most recent high-
    confidence signal within the lookback window, converting it into a
    backtestable Signal. All DB errors are caught — the adapter returns [] and
    logs a warning rather than crashing the backtest.

    Attributes:
        _session_factory: SQLAlchemy session factory bound to the target engine.
        _min_confidence: Minimum signal confidence in [0.0, 1.0]. Rows below
            this threshold are excluded via the SQL WHERE clause.
        _lookback_hours: How many hours before snapshot.ts to search for signals.
        _contracts: Number of contracts per generated signal.

    Args:
        db_url: SQLAlchemy-compatible database URL (e.g. ``postgresql://...`` or
            ``sqlite:///path/to/file.db``).
        min_confidence: Minimum confidence threshold [0.0, 1.0]. Default 0.5.
        lookback_hours: Hours before snapshot.ts to include. Default 24.
        contracts_per_signal: Contracts to request per signal. Default 1.
    """

    def __init__(
        self,
        db_url: str,
        min_confidence: float = 0.5,
        lookback_hours: int = 24,
        contracts_per_signal: int = 1,
    ) -> None:
        """Initialise InsiderTrackerAdapter.

        Args:
            db_url: SQLAlchemy database URL for the Insider Tracker database.
            min_confidence: Signal confidence floor; signals below this are ignored.
            lookback_hours: How many hours back from snapshot.ts to search.
            contracts_per_signal: Number of contracts per generated Signal.
        """
        engine = create_engine(db_url, pool_pre_ping=True)
        self._session_factory = sessionmaker(engine)
        self._min_confidence = min_confidence
        self._lookback_hours = lookback_hours
        self._contracts = contracts_per_signal
        self._log = logger.bind(strategy="InsiderTrackerAdapter")

    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]:
        """Query the Insider Tracker DB and return a Signal if a match is found.

        Look-ahead safe: only queries ``detected_at < snapshot.ts``.
        Returns [] immediately if the ticker is already held.
        Catches all DB errors, logs a warning, and returns [] — never raises.

        Args:
            snapshot: Market bar. Uses .ticker (str), .ts (naive UTC datetime),
                and .close_price (int cents) to build the SQL query.
            open_positions: Held positions. Ticker already held → no new signal.

        Returns:
            List of up to one Signal if a qualifying row is found, else [].
        """
        held_tickers = {p.ticker for p in open_positions}
        if snapshot.ticker in held_tickers:
            return []

        window_start = snapshot.ts - timedelta(hours=self._lookback_hours)
        window_end = snapshot.ts  # strictly less-than in SQL

        try:
            with self._session_factory() as session:
                rows = session.execute(
                    _SIGNAL_QUERY,
                    {
                        "ticker": snapshot.ticker,
                        "start": window_start.isoformat(),
                        "end": window_end.isoformat(),
                        "min_conf": self._min_confidence,
                    },
                ).fetchall()
        except Exception:
            self._log.warning(
                "insider_adapter_db_error",
                ticker=snapshot.ticker,
                exc_info=True,
            )
            return []

        if not rows:
            return []

        row = rows[0]
        signal_type: str = row[0]
        confidence: float = row[1]
        raw_details = row[2]

        # Details may arrive as a JSON string (SQLite) or a dict (PostgreSQL JSONB)
        details: dict = raw_details if isinstance(raw_details, dict) else json.loads(raw_details or "{}")

        direction = self._resolve_direction(signal_type, details, snapshot.close_price)

        self._log.info(
            "insider_adapter_signal",
            ticker=snapshot.ticker,
            signal_type=signal_type,
            confidence=confidence,
            direction=direction,
        )

        # Set limit_price above close to absorb the spread (fill engine adds half-spread)
        limit_price = min(99, snapshot.close_price + 2) if direction == "yes" else max(1, snapshot.close_price - 2)

        return [
            Signal(
                ticker=snapshot.ticker,
                direction=direction,
                contracts=self._contracts,
                limit_price=limit_price,
                reason=f"insider_tracker:{signal_type}:confidence={confidence:.2f}",
            )
        ]

    @staticmethod
    def _resolve_direction(
        signal_type: str,
        details: dict,
        close_price: int,
    ) -> str:
        """Determine trade direction from signal type and details.

        For ``price_move`` signals, the direction is inferred from whether the
        last price is above or below the previous price. For all other signal
        types (``volume_spike``, ``timing_cluster``), direction defaults to
        ``'yes'``.

        Args:
            signal_type: Insider Tracker signal type string.
            details: Parsed details dict from the signals row.
            close_price: Current bar close price in cents (fallback for edge cases).

        Returns:
            ``'yes'`` or ``'no'`` as a string literal.
        """
        if signal_type == "price_move":
            last_price = details.get("last_price")
            prev_price = details.get("prev_price")
            if last_price is not None and prev_price is not None:
                return "yes" if last_price > prev_price else "no"
            # Fallback when detail keys are missing — can't determine direction
            return "yes"

        # volume_spike, timing_cluster, and any unknown types default to 'yes'
        return "yes"
