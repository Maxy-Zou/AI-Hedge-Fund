"""Risk guard for trade execution — hard limits, in-flight detection, duplicate dedup.

Hard limits are module-level constants (EXEC-03, EXEC-04) — never loaded from config.
Exposure is always derived from a fresh DB query, never cached in memory.
In-flight check uses a 60s window to handle crash recovery (Pitfall: stale pending rows).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session, sessionmaker

from kalshi_tracker.db.models import Trade
from kalshi_tracker.execution.types import ApprovalResult

# Hard limits — code constants per EXEC-03 and EXEC-04.
# These are NOT config values. Changing them requires a code review + deployment.
MAX_PER_TRADE_CENTS: int = 5_000       # $50 — NOT from config (EXEC-03)
MAX_TOTAL_EXPOSURE_CENTS: int = 50_000  # $500 — NOT from config (EXEC-04)

_IN_FLIGHT_WINDOW_SECONDS: int = 60    # stale pending rows beyond 60s are timed out
_DUPLICATE_WINDOW_SECONDS: int = 300   # 5-minute dedup window for filled trades

logger = structlog.get_logger(__name__)


class RiskGuard:
    """Hard gate that approves or rejects signals before execution.

    Enforces:
    - Per-trade cost cap (EXEC-03)
    - Total live exposure cap (EXEC-04)
    - Duplicate signal dedup (EXEC-05)
    - In-flight order detection (EXEC-06)

    Every check uses a fresh DB query — no cached state.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """Initialize RiskGuard with a session factory.

        Args:
            session_factory: SQLAlchemy sessionmaker for DB queries.
        """
        self._session_factory = session_factory
        self._log = logger.bind(guard="risk_guard")

    def approve(self, signal: object) -> ApprovalResult:
        """Evaluate a signal against all risk rules. Returns an ApprovalResult.

        Check order (designed so unit-test mock fixtures map to exactly one block):
        1. Per-trade cost cap — no DB needed (blocks if contracts*price > MAX_PER_TRADE_CENTS)
        2. Total exposure cap — DB query (blocks if adding this trade exceeds $500 total)
        3. Duplicate check — DB query (blocks if live filled trade within 300s for same ticker)
        4. In-flight check — DB query (blocks if pending trade within 60s for same ticker)

        Args:
            signal: Signal ORM object with .ticker, .details dict.

        Returns:
            ApprovalResult(approved=False, reason=...) if any check fails.
            ApprovalResult(approved=True, reason='approved', trade_cost_cents=...) otherwise.
        """
        price_cents: int = signal.details.get("current_price", 0)  # type: ignore[attr-defined]
        contracts: int = signal.details.get("contracts", 1)  # type: ignore[attr-defined]
        trade_cost_cents = contracts * price_cents

        # 1. Per-trade cost cap (EXEC-03) — no DB needed
        if trade_cost_cents > MAX_PER_TRADE_CENTS:
            self._log.info(
                "trade_blocked",
                ticker=signal.ticker,  # type: ignore[attr-defined]
                reason="per_trade_cap",
                trade_cost_cents=trade_cost_cents,
            )
            return ApprovalResult(approved=False, reason="per_trade_cap", trade_cost_cents=0)

        with self._session_factory() as session:
            existing_trades = self._fetch_live_trades(session)

            # 2. Total exposure cap (EXEC-04)
            current_exposure = _sum_exposure(existing_trades)
            if current_exposure + trade_cost_cents > MAX_TOTAL_EXPOSURE_CENTS:
                self._log.info(
                    "trade_blocked",
                    ticker=signal.ticker,  # type: ignore[attr-defined]
                    reason="total_exposure_cap",
                    current_exposure=current_exposure,
                    trade_cost_cents=trade_cost_cents,
                )
                return ApprovalResult(
                    approved=False, reason="total_exposure_cap", trade_cost_cents=0
                )

            # 3. Duplicate check (EXEC-05) — same ticker, live filled, within 300s
            if self._has_duplicate(signal.ticker, session):  # type: ignore[attr-defined]
                self._log.info(
                    "trade_blocked",
                    ticker=signal.ticker,  # type: ignore[attr-defined]
                    reason="duplicate",
                    trade_cost_cents=0,
                )
                return ApprovalResult(approved=False, reason="duplicate", trade_cost_cents=0)

            # 4. In-flight order check (EXEC-06) — same ticker, pending, within 60s
            if self._has_in_flight(signal.ticker, session):  # type: ignore[attr-defined]
                self._log.info(
                    "trade_blocked",
                    ticker=signal.ticker,  # type: ignore[attr-defined]
                    reason="in_flight",
                    trade_cost_cents=0,
                )
                return ApprovalResult(approved=False, reason="in_flight", trade_cost_cents=0)

        self._log.info(
            "trade_approved",
            ticker=signal.ticker,  # type: ignore[attr-defined]
            trade_cost_cents=trade_cost_cents,
        )
        return ApprovalResult(
            approved=True, reason="approved", trade_cost_cents=trade_cost_cents
        )

    def _fetch_live_trades(self, session: Session) -> list:
        """Fetch all live trades (pending or filled) for exposure calculation.

        Args:
            session: Active DB session.

        Returns:
            List of Trade objects with mode='live' and status in ('pending', 'filled').
        """
        rows = (
            session.query(Trade)
            .filter(
                Trade.mode == "live",
                Trade.status.in_(["pending", "filled"]),
            )
            .all()
        )
        # Defensive Python-side filter (ensures unit test mocks with mixed fixtures work)
        return [t for t in rows if t.mode == "live" and t.status in ("pending", "filled")]

    def _has_in_flight(self, ticker: str, session: Session) -> bool:
        """Check if a pending trade for this ticker exists within the in-flight window.

        Stale pending rows older than _IN_FLIGHT_WINDOW_SECONDS are ignored — they are
        assumed to be crash remnants (Pitfall: stale pending rows from aborted runs).

        Args:
            ticker: Market ticker to check.
            session: Active DB session.

        Returns:
            True if a pending trade exists within the last 60 seconds.
        """
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=_IN_FLIGHT_WINDOW_SECONDS)
        rows = (
            session.query(Trade)
            .filter(
                Trade.ticker == ticker,
                Trade.status == "pending",
                Trade.placed_at > cutoff,
            )
            .all()
        )
        # Defensive Python-side filter for unit test mock compatibility
        return any(
            t.ticker == ticker and t.status == "pending" and t.placed_at > cutoff
            for t in rows
        )

    def _has_duplicate(self, ticker: str, session: Session) -> bool:
        """Check if a live filled trade for this ticker exists within the dedup window.

        Only live trades count — paper trades should not suppress live signals.

        Args:
            ticker: Market ticker to check.
            session: Active DB session.

        Returns:
            True if a live filled trade exists within the last 300 seconds.
        """
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=_DUPLICATE_WINDOW_SECONDS)
        rows = (
            session.query(Trade)
            .filter(
                Trade.ticker == ticker,
                Trade.status == "filled",
                Trade.mode == "live",
                Trade.placed_at > cutoff,
            )
            .all()
        )
        # Defensive Python-side filter for unit test mock compatibility
        return any(
            t.ticker == ticker
            and t.status == "filled"
            and t.mode == "live"
            and t.placed_at > cutoff
            for t in rows
        )

    def _total_open_exposure(self, session: Session) -> int:
        """Compute total live exposure from pending and filled trades.

        Sums contracts * price_cents for all live trades.

        Args:
            session: Active DB session.

        Returns:
            Total exposure in cents.
        """
        rows = self._fetch_live_trades(session)
        return _sum_exposure(rows)


def _sum_exposure(trades: list) -> int:
    """Sum contracts * price_cents for a list of trade objects.

    Args:
        trades: List of Trade-like objects with .contracts and .price_cents attributes.

    Returns:
        Total exposure in cents.
    """
    return sum(t.contracts * t.price_cents for t in trades)
