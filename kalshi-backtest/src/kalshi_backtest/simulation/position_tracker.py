"""PositionTracker — position lifecycle from fill → open → closed (via settlement or exit).

Manages the state machine for all open and closed positions during a backtest run.
Each Fill creates an open Position. Positions are closed either by:
- Settlement: the market resolves and all open positions for that ticker are settled at $1 or $0
- Exit: a position is explicitly closed at a mark-to-market price before settlement

PositionTracker also produces the final trade log (DataFrame) and daily P&L Series
consumed by BacktestResult and the metrics layer (Phase 3).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import pandas as pd
import structlog

from kalshi_backtest.simulation.fill_engine import (
    Fill,
    calculate_exit_pnl,
    calculate_settlement_pnl,
)
from kalshi_backtest.simulation.protocol import Position

logger = structlog.get_logger(__name__).bind(component="PositionTracker")


# ---------------------------------------------------------------------------
# ClosedPosition — immutable record of a completed trade
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClosedPosition:
    """Immutable record of a fully closed position, including P&L.

    Created by PositionTracker.settle() or PositionTracker.close().
    All Position fields are carried forward; exit info and P&L are added.

    Attributes:
        ticker: Kalshi market ticker.
        direction: Contract side — 'yes' or 'no'.
        contracts: Number of contracts held.
        entry_price: Fill price at open (cents).
        entry_ts: Timestamp of the opening fill (naive UTC).
        fill_id: Unique ID of the opening fill.
        exit_price: Exit price in cents (100 for YES win, 0 for YES loss, etc.).
        exit_ts: Timestamp of the closing event (naive UTC).
        pnl_cents: Net P&L in integer cents (positive = profit).
        fee_cents: Taker fee paid at entry (cents).
        exit_reason: 'settlement', 'position_close', or custom reason.
    """

    ticker: str
    direction: Literal["yes", "no"]
    contracts: int
    entry_price: int
    entry_ts: datetime
    fill_id: str
    exit_price: int
    exit_ts: datetime
    pnl_cents: int
    fee_cents: int
    exit_reason: str


# ---------------------------------------------------------------------------
# PositionTracker — open/close/settle state machine
# ---------------------------------------------------------------------------


class PositionTracker:
    """Tracks open and closed positions across a full simulation run.

    Thread-safety: Not thread-safe. Designed for single-threaded bar-by-bar
    replay within a BacktestRunner.
    """

    def __init__(self) -> None:
        """Initialize with empty open and closed position stores."""
        # ticker -> list of open positions for that ticker
        self._open: dict[str, list[Position]] = {}
        self._closed: list[ClosedPosition] = []
        # fill_id -> entry fee_cents (carried into ClosedPosition on settlement)
        self._entry_fees: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def open_positions(self) -> list[Position]:
        """All currently open positions across all tickers."""
        result = []
        for positions in self._open.values():
            result.extend(positions)
        return result

    @property
    def closed_positions(self) -> list[ClosedPosition]:
        """All closed positions (settled or exited) in chronological order."""
        return list(self._closed)

    # ------------------------------------------------------------------
    # Mutating operations
    # ------------------------------------------------------------------

    def open(self, fill: Fill) -> Position:
        """Create a Position from a Fill and add it to open positions.

        Args:
            fill: The executed fill from FillEngine.try_fill().

        Returns:
            The newly created Position.
        """
        position = Position(
            ticker=fill.ticker,
            direction=fill.direction,
            contracts=fill.contracts,
            entry_price=fill.fill_price,
            entry_ts=fill.ts,
            fill_id=fill.fill_id,
        )
        if fill.ticker not in self._open:
            self._open[fill.ticker] = []
        self._open[fill.ticker].append(position)
        # Stash the entry fee so settle() can carry it into ClosedPosition
        self._entry_fees[fill.fill_id] = fill.fee_cents
        logger.debug(
            "position_opened",
            ticker=fill.ticker,
            direction=fill.direction,
            contracts=fill.contracts,
            entry_price=fill.fill_price,
        )
        return position

    def close(self, position: Position, fill: Fill) -> ClosedPosition:
        """Close a position at a mark-to-market price via a closing fill.

        Removes the position from open, computes exit P&L, and adds to closed.

        Args:
            position: The open Position to close.
            fill: The closing Fill from FillEngine.close_position().

        Returns:
            The ClosedPosition record with computed pnl_cents.
        """
        # Remove from open
        ticker = position.ticker
        if ticker in self._open and position in self._open[ticker]:
            self._open[ticker].remove(position)
            if not self._open[ticker]:
                del self._open[ticker]

        pnl = calculate_exit_pnl(
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=fill.fill_price,
            contracts=position.contracts,
        )
        closed = ClosedPosition(
            ticker=position.ticker,
            direction=position.direction,
            contracts=position.contracts,
            entry_price=position.entry_price,
            entry_ts=position.entry_ts,
            fill_id=position.fill_id,
            exit_price=fill.fill_price,
            exit_ts=fill.ts,
            pnl_cents=pnl,
            fee_cents=fill.fee_cents,
            exit_reason=fill.reason,
        )
        self._closed.append(closed)
        return closed

    def settle(self, ticker: str, result: str, ts: datetime) -> list[ClosedPosition]:
        """Settle all open positions for a ticker at binary contract resolution.

        Each contract either wins (pays $1.00) or loses (pays $0.00) based on
        whether the result matches the position's direction.

        Args:
            ticker: The market ticker being settled.
            result: Settlement result — 'yes' or 'no'.
            ts: Timestamp of settlement (naive UTC).

        Returns:
            List of ClosedPosition records for all settled positions.
        """
        positions = self._open.pop(ticker, [])
        settled: list[ClosedPosition] = []

        for position in positions:
            pnl = calculate_settlement_pnl(
                direction=position.direction,
                entry_price=position.entry_price,
                contracts=position.contracts,
                result=result,
            )
            # Exit price: winning side pays 100, losing side pays 0
            won = (position.direction == result)
            exit_price = 100 if won else 0

            entry_fee = self._entry_fees.pop(position.fill_id, 0)
            closed = ClosedPosition(
                ticker=position.ticker,
                direction=position.direction,
                contracts=position.contracts,
                entry_price=position.entry_price,
                entry_ts=position.entry_ts,
                fill_id=position.fill_id,
                exit_price=exit_price,
                exit_ts=ts,
                pnl_cents=pnl,
                fee_cents=entry_fee,
                exit_reason="settlement",
            )
            self._closed.append(closed)
            settled.append(closed)

        if positions:
            logger.info(
                "positions_settled",
                ticker=ticker,
                result=result,
                count=len(positions),
            )

        return settled

    # ------------------------------------------------------------------
    # Output methods
    # ------------------------------------------------------------------

    def to_trade_log(self) -> pd.DataFrame:
        """Build the full trade log as a DataFrame.

        Returns:
            pd.DataFrame with columns: ticker, direction, contracts, entry_price,
            entry_ts, exit_price, exit_ts, pnl_cents, fee_cents, exit_reason.
            Empty DataFrame (with columns) if no closed positions.
        """
        columns = [
            "ticker", "direction", "contracts",
            "entry_price", "entry_ts", "exit_price", "exit_ts",
            "pnl_cents", "fee_cents", "exit_reason",
        ]
        if not self._closed:
            return pd.DataFrame(columns=columns)

        rows = [
            {
                "ticker": cp.ticker,
                "direction": cp.direction,
                "contracts": cp.contracts,
                "entry_price": cp.entry_price,
                "entry_ts": cp.entry_ts,
                "exit_price": cp.exit_price,
                "exit_ts": cp.exit_ts,
                "pnl_cents": cp.pnl_cents,
                "fee_cents": cp.fee_cents,
                "exit_reason": cp.exit_reason,
            }
            for cp in self._closed
        ]
        return pd.DataFrame(rows, columns=columns)

    def to_daily_pnl_series(self) -> pd.Series:
        """Aggregate P&L by calendar date.

        Groups pnl_cents by exit_ts.date() and sums within each day.

        Returns:
            pd.Series with datetime.date index and integer pnl_cents values.
            Empty Series if no closed positions.
        """
        if not self._closed:
            return pd.Series(dtype=int)

        daily: dict[date, int] = {}
        for cp in self._closed:
            d = cp.exit_ts.date()
            daily[d] = daily.get(d, 0) + cp.pnl_cents

        return pd.Series(daily, dtype=int)
