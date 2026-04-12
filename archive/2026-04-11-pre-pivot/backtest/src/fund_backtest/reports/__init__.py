"""Report generation: PDF tearsheet and CSV/JSON exports.

Public API:
  - TearsheetBuilder: generates a matplotlib PDF tearsheet with equity curve,
    drawdown fill, monthly heatmap, and metrics/cost table.
  - ExportBuilder: writes CSV (daily_returns, positions, trade_log) and JSON
    (metrics.json) with cost assumptions embedded in every output file.

Usage:
    from fund_backtest.reports import TearsheetBuilder, ExportBuilder
"""
from fund_backtest.reports.exporter import ExportBuilder
from fund_backtest.reports.tearsheet import TearsheetBuilder

__all__ = ["TearsheetBuilder", "ExportBuilder"]
