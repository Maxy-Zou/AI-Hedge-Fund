"""kalshi_backtest.metrics — portfolio analytics for Kalshi backtest results.

Public exports:
    BacktestMetrics: Frozen Pydantic model with all scalar and series metrics.
    MetricsCalculator: Converts BacktestResult → BacktestMetrics via quantstats.
    export_trade_log: Writes a CSV trade log with dollar-converted P&L columns.
"""
from __future__ import annotations

from kalshi_backtest.metrics.calculator import BacktestMetrics, MetricsCalculator
from kalshi_backtest.metrics.trade_log import export_trade_log

__all__ = ["BacktestMetrics", "MetricsCalculator", "export_trade_log"]
