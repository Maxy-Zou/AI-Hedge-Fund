"""Simulation engine public API.

Import from this module to access the Strategy Protocol and core data contracts:
    from kalshi_backtest.simulation import Strategy, Signal, Position, MarketSnapshot, build_snapshot
"""
from kalshi_backtest.simulation.protocol import Position, Signal, Strategy
from kalshi_backtest.simulation.snapshot import MarketSnapshot, build_snapshot

__all__ = ["Strategy", "Signal", "Position", "MarketSnapshot", "build_snapshot"]
