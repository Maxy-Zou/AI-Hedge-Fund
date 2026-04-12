"""Strategy plugin package for kalshi_backtest.

Exports the STRATEGY_REGISTRY — a dict mapping string keys to Strategy classes.
The registry is populated at import time; InsiderTrackerAdapter is only added
when sqlalchemy is available (it is a soft dependency).

Available strategies:
    "pass-through"   — _PassThroughStrategy: emits no signals (baseline)
    "example"        — ExampleStrategy: buys YES when price < threshold
    "insider-tracker"— InsiderTrackerAdapter: reads signals from Insider Tracker DB
                       (only when sqlalchemy is installed)

Usage:
    from kalshi_backtest.strategies import STRATEGY_REGISTRY, ExampleStrategy

    StrategyClass = STRATEGY_REGISTRY["example"]
    strategy = StrategyClass(buy_threshold=30)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kalshi_backtest.simulation.protocol import Position, Signal
    from kalshi_backtest.simulation.snapshot import MarketSnapshot

from kalshi_backtest.strategies.example import ExampleStrategy


class _PassThroughStrategy:
    """No-op strategy that never generates signals.

    Used as a baseline or placeholder when no real strategy is wired in.
    Satisfies the Strategy Protocol via structural subtyping.
    """

    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]:
        """Return an empty signal list unconditionally.

        Args:
            snapshot: Market bar snapshot (unused).
            open_positions: Currently held positions (unused).

        Returns:
            Always [].
        """
        return []


STRATEGY_REGISTRY: dict[str, type] = {
    "pass-through": _PassThroughStrategy,
    "example": ExampleStrategy,
}

# InsiderTrackerAdapter is only available when sqlalchemy is installed.
try:
    from kalshi_backtest.strategies.insider_tracker import InsiderTrackerAdapter

    STRATEGY_REGISTRY["insider-tracker"] = InsiderTrackerAdapter
except ImportError:
    InsiderTrackerAdapter = None  # type: ignore[assignment,misc]

__all__ = [
    "STRATEGY_REGISTRY",
    "ExampleStrategy",
    "InsiderTrackerAdapter",
    "_PassThroughStrategy",
]
