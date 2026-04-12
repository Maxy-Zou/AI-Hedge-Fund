"""kalshi_backtest.metrics — portfolio analytics for Kalshi backtest results.

Public exports:
    BacktestMetrics: Frozen Pydantic model with all scalar and series metrics.
    MetricsCalculator: Converts BacktestResult → BacktestMetrics via quantstats.
    export_trade_log: Writes a CSV trade log with dollar-converted P&L columns.
    build_dashboard: Builds a 4-panel Plotly Figure from BacktestMetrics + trade log.
    compute_category_breakdown: Groups trade log rows by ticker prefix.
    DashboardBuilder: Convenience class that writes an HTML dashboard to disk.
"""
from __future__ import annotations

from kalshi_backtest.metrics.calculator import BacktestMetrics, MetricsCalculator
from kalshi_backtest.metrics.dashboard import DashboardBuilder, build_dashboard, compute_category_breakdown
from kalshi_backtest.metrics.trade_log import export_trade_log

__all__ = [
    "BacktestMetrics",
    "MetricsCalculator",
    "export_trade_log",
    "build_dashboard",
    "compute_category_breakdown",
    "DashboardBuilder",
]
