"""FillEngine — Kalshi fee formula, fill price simulation, and binary P&L calculation.

This module is the financial math layer of the simulator. Any error here would corrupt
all backtest results, so every public function has corresponding unit tests.

Key formulas:
- Fee:        ceil(0.07 * C * P * (1-P))  where P is price fraction in [0.0, 1.0]
- Fill price: mid + ceil(spread/2) for YES buys; mid - ceil(spread/2) for YES sells
- Settlement: (100 - entry) * contracts for wins; -entry * contracts for losses
- Exit:       (exit_price - entry_price) * contracts for YES positions
              (entry_price - exit_price) * contracts for NO positions

Usage:
    engine = FillEngine(spread_floor=1)
    fill = engine.try_fill(signal, snapshot)  # None if limit not fillable
    closing_fill = engine.close_position(position, snapshot)
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import structlog

from kalshi_backtest.simulation.protocol import Position, Signal
from kalshi_backtest.simulation.snapshot import MarketSnapshot

logger = structlog.get_logger(__name__).bind(component="FillEngine")


# ---------------------------------------------------------------------------
# Fill dataclass — immutable record of an executed trade
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fill:
    """Immutable record of a single executed trade.

    Attributes:
        fill_id: Unique identifier (uuid4 string).
        ticker: Kalshi market ticker.
        direction: Contract side traded — 'yes' or 'no'.
        contracts: Number of contracts executed.
        fill_price: Execution price in cents [0, 100].
        fee_cents: Kalshi taker fee in integer cents.
        ts: Bar timestamp at time of fill (naive UTC).
        reason: Reason from the originating signal or close event.
    """

    fill_id: str
    ticker: str
    direction: Literal["yes", "no"]
    contracts: int
    fill_price: int
    fee_cents: int
    ts: datetime
    reason: str


# ---------------------------------------------------------------------------
# Pure functions — easily unit-testable in isolation
# ---------------------------------------------------------------------------


def calculate_fee_cents(contracts: int, price_fraction: float) -> int:
    """Kalshi taker fee in integer cents.

    Formula: max(1, ceil(0.07 * C * P * (1-P)))
    The minimum fee is always 1 cent per transaction.

    Args:
        contracts: Number of contracts. Must be >= 1.
        price_fraction: Price as a fraction in [0.0, 1.0], NOT cents.
                        E.g., 50 cents = 0.50.

    Returns:
        Fee in integer cents (minimum 1).

    Raises:
        ValueError: If contracts <= 0 or price_fraction outside [0.0, 1.0].
    """
    if contracts <= 0:
        raise ValueError(f"contracts must be >= 1, got {contracts}")
    if not 0.0 <= price_fraction <= 1.0:
        raise ValueError(f"price_fraction must be in [0.0, 1.0], got {price_fraction}")

    raw = 0.07 * contracts * price_fraction * (1.0 - price_fraction)
    return max(1, math.ceil(raw))


def simulate_fill_price(
    direction: str,
    limit_price: int,
    mid_price: int,
    spread_floor: int = 1,
) -> int | None:
    """Simulate fill price given a limit order and market mid price.

    Fill model:
    - YES buy:  fills at mid + ceil(spread_floor/2). Returns None if limit < fill_price.
    - NO buy:   fills at mid - ceil(spread_floor/2) (YES side). The NO cost is
                (100 - yes_fill). Returns None if limit < (100 - yes_fill).
    - YES sell: fills at mid - ceil(spread_floor/2). Returns None if limit > fill_price.
                (Not yet needed; close_position handles this internally.)

    Args:
        direction: 'yes' or 'no' — which side is being bought.
        limit_price: Maximum price willing to pay (cents). For NO, this is the NO price.
        mid_price: Current market mid price in YES cents.
        spread_floor: Minimum half-spread in cents (default 1).

    Returns:
        Fill price in YES cents if fillable, None otherwise.
    """
    half_spread = math.ceil(spread_floor / 2)

    if direction == "yes":
        # YES buy: pay ask = mid + half_spread
        fill_yes = min(100, mid_price + half_spread)
        if limit_price >= fill_yes:
            return fill_yes
        return None

    else:  # direction == "no"
        # NO buy: buy NO at (100 - yes_bid). YES bid = mid - half_spread.
        fill_yes = max(0, mid_price - half_spread)
        no_cost = 100 - fill_yes
        if limit_price >= no_cost:
            return fill_yes
        return None


def calculate_settlement_pnl(
    direction: str,
    entry_price: int,
    contracts: int,
    result: str,
) -> int:
    """Hold-to-settlement P&L in cents.

    Binary contract mechanics:
    - YES win:  each YES contract pays $1.00 (100 cents) → profit = (100 - entry) * contracts
    - YES loss: each YES contract pays $0.00 → loss = -entry * contracts
    - NO win:   each NO contract pays $1.00 (100 cents) → profit = (100 - entry) * contracts
    - NO loss:  each NO contract pays $0.00 → loss = -entry * contracts

    The formula is symmetric: win = (100 - entry) * contracts, loss = -entry * contracts,
    where "win" means the result matches the position's direction.

    Args:
        direction: Position side — 'yes' or 'no'.
        entry_price: Fill price in cents [0, 100].
        contracts: Number of contracts held.
        result: Settlement result — 'yes' or 'no'. Must match direction for a win.

    Returns:
        P&L in integer cents (positive = profit, negative = loss).

    Raises:
        ValueError: If result is not 'yes' or 'no'.
    """
    if result not in ("yes", "no"):
        raise ValueError(f"result must be 'yes' or 'no', got {result!r}")

    won = (direction == result)
    if won:
        return (100 - entry_price) * contracts
    else:
        return -entry_price * contracts


def calculate_exit_pnl(
    direction: str,
    entry_price: int,
    exit_price: int,
    contracts: int,
) -> int:
    """Mark-to-market exit P&L in cents (before fees).

    For YES positions: P&L = (exit_price - entry_price) * contracts
    For NO positions:  P&L = (entry_price - exit_price) * contracts
        (because NO price moves inversely to YES price; entry_no = 100 - entry_yes)

    Args:
        direction: Position side — 'yes' or 'no'.
        entry_price: Original fill price in cents [0, 100].
        exit_price: Exit fill price in cents [0, 100]. For NO, this is the YES price.
        contracts: Number of contracts.

    Returns:
        P&L in integer cents.
    """
    if direction == "yes":
        return (exit_price - entry_price) * contracts
    else:  # "no"
        # NO P&L is inverse of YES movement
        return (entry_price - exit_price) * contracts


# ---------------------------------------------------------------------------
# FillEngine class — stateful wrapper for convenience
# ---------------------------------------------------------------------------


class FillEngine:
    """Stateful convenience wrapper for fill execution and position closing.

    Args:
        spread_floor: Minimum spread applied when computing fill prices (cents).
    """

    def __init__(self, spread_floor: int = 1) -> None:
        self._spread_floor = spread_floor

    def try_fill(self, signal: Signal, snapshot: MarketSnapshot) -> Fill | None:
        """Attempt to fill a signal at current market prices.

        Uses close_price as the market mid price. If the signal's limit_price
        cannot be filled given the spread, returns None.

        Args:
            signal: Signal from the strategy with direction, contracts, limit_price.
            snapshot: Current bar snapshot providing the mid price.

        Returns:
            Fill if limit is fillable, None otherwise.
        """
        fill_price = simulate_fill_price(
            direction=signal.direction,
            limit_price=signal.limit_price,
            mid_price=snapshot.close_price,
            spread_floor=self._spread_floor,
        )
        if fill_price is None:
            return None

        fee = calculate_fee_cents(signal.contracts, fill_price / 100.0)

        return Fill(
            fill_id=str(uuid.uuid4()),
            ticker=signal.ticker,
            direction=signal.direction,
            contracts=signal.contracts,
            fill_price=fill_price,
            fee_cents=fee,
            ts=snapshot.ts,
            reason=signal.reason,
        )

    def close_position(self, position: Position, snapshot: MarketSnapshot) -> Fill | None:
        """Create a closing fill for an open position at current market prices.

        For a YES position, we sell YES (fill at YES bid = mid - half_spread).
        For a NO position, we sell NO (fill at NO bid = 100 - (mid + half_spread)).
        Uses a high limit price to always fill unless market is at extreme (0 or 100).

        Args:
            position: The open position to close.
            snapshot: Current bar snapshot providing the mid price.

        Returns:
            Fill for the closing trade, or None if market price makes fill impossible.
        """
        # To close YES: sell YES → fill at YES bid (mid - half_spread)
        # To close NO: sell NO → the YES ask moves against us (mid + half_spread)
        # We express close as a trade in the same direction (position direction)
        # at the worst fillable price
        half_spread = math.ceil(self._spread_floor / 2)

        if position.direction == "yes":
            # Selling YES: fill at bid = mid - half_spread
            fill_yes = max(0, snapshot.close_price - half_spread)
        else:
            # Selling NO: equivalent to buying YES at ask; NO proceeds = 100 - yes_ask
            fill_yes = min(100, snapshot.close_price + half_spread)

        fee = calculate_fee_cents(position.contracts, fill_yes / 100.0)

        return Fill(
            fill_id=str(uuid.uuid4()),
            ticker=position.ticker,
            direction=position.direction,
            contracts=position.contracts,
            fill_price=fill_yes,
            fee_cents=fee,
            ts=snapshot.ts,
            reason="position_close",
        )
