"""Simulation engine public API.

Import from this module to access the Strategy Protocol, core data contracts,
the BarIterator replay engine, and the FillEngine financial math layer:

    from kalshi_backtest.simulation import (
        Strategy, Signal, Position, MarketSnapshot, build_snapshot,
        BarIterator, FillEngine, Fill,
        calculate_fee_cents, simulate_fill_price,
        calculate_settlement_pnl, calculate_exit_pnl,
    )
"""
from kalshi_backtest.simulation.bar_iterator import BarIterator
from kalshi_backtest.simulation.fill_engine import (
    Fill,
    FillEngine,
    calculate_exit_pnl,
    calculate_fee_cents,
    calculate_settlement_pnl,
    simulate_fill_price,
)
from kalshi_backtest.simulation.protocol import Position, Signal, Strategy
from kalshi_backtest.simulation.snapshot import MarketSnapshot, build_snapshot

__all__ = [
    "Strategy",
    "Signal",
    "Position",
    "MarketSnapshot",
    "build_snapshot",
    "BarIterator",
    "FillEngine",
    "Fill",
    "calculate_fee_cents",
    "simulate_fill_price",
    "calculate_settlement_pnl",
    "calculate_exit_pnl",
]
