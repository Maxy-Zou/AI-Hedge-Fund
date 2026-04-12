"""Strategy Protocol and core trade data contracts for the simulation engine.

Design rationale:
- Strategy uses structural subtyping (typing.Protocol) so strategies can implement
  generate_signals() without importing anything from this codebase. This keeps
  strategies fully decoupled from engine internals.
- @runtime_checkable enables isinstance(obj, Strategy) checks in tests and runner
  validation without requiring inheritance.
- Signal and Position are frozen Pydantic models — fund-wide immutability convention.
  They carry all fields required by FillEngine and PositionTracker.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, field_validator

if TYPE_CHECKING:
    from kalshi_backtest.simulation.snapshot import MarketSnapshot


@runtime_checkable
class Strategy(Protocol):
    """Plugin interface for any Kalshi backtesting strategy.

    Implement generate_signals() to define a strategy. No inheritance required —
    structural subtyping means any class with this method satisfies the protocol.

    Args:
        snapshot: Look-ahead-safe view of a market at a point in time.
        open_positions: Currently held positions for this market.

    Returns:
        List of Signal orders to submit on this bar.
    """

    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]: ...


class Signal(BaseModel):
    """An order intent produced by a Strategy for a single bar.

    Immutable — once created by generate_signals(), the engine does not modify it.
    FillEngine consumes this to determine whether a fill occurs given market prices.

    Attributes:
        ticker: Kalshi market ticker (e.g., 'KXBTC-24DEC-T50000').
        direction: Contract side — 'yes' or 'no'.
        contracts: Number of contracts to trade. Must be >= 1.
        limit_price: Maximum price willing to pay (yes side) in cents [0, 100].
        reason: Human-readable rationale from the strategy (used in trade log).
    """

    model_config = {"frozen": True}

    ticker: str
    direction: Literal["yes", "no"]
    contracts: int
    limit_price: int
    reason: str

    @field_validator("contracts")
    @classmethod
    def contracts_minimum_one(cls, v: int) -> int:
        """Contracts must be >= 1 — partial contracts are not supported."""
        if v < 1:
            raise ValueError(f"contracts must be >= 1, got {v}")
        return v

    @field_validator("limit_price")
    @classmethod
    def limit_price_range(cls, v: int) -> int:
        """Limit price must be in [0, 100] cents."""
        if not 0 <= v <= 100:
            raise ValueError(f"limit_price {v} out of valid range [0, 100]")
        return v


class Position(BaseModel):
    """An open position resulting from a filled Signal.

    Immutable record of an executed trade. PositionTracker holds a list of these.
    On settlement or exit, these are converted to closed trade records for P&L.

    Attributes:
        ticker: Kalshi market ticker.
        direction: Contract side held — 'yes' or 'no'.
        contracts: Number of contracts held. Must be >= 1.
        entry_price: Fill price in cents [0, 100].
        entry_ts: Timestamp of the fill (naive UTC).
        fill_id: Unique identifier for the fill that opened this position.
    """

    model_config = {"frozen": True}

    ticker: str
    direction: Literal["yes", "no"]
    contracts: int
    entry_price: int
    entry_ts: datetime
    fill_id: str

    @field_validator("contracts")
    @classmethod
    def contracts_minimum_one(cls, v: int) -> int:
        """Contracts must be >= 1."""
        if v < 1:
            raise ValueError(f"contracts must be >= 1, got {v}")
        return v

    @field_validator("entry_price")
    @classmethod
    def entry_price_range(cls, v: int) -> int:
        """Entry price must be in [0, 100] cents."""
        if not 0 <= v <= 100:
            raise ValueError(f"entry_price {v} out of valid range [0, 100]")
        return v
