"""CLI entry point for Kalshi Backtesting Engine.

Commands are wired in Phase 1, Plan 05.
"""
from __future__ import annotations

import typer

app = typer.Typer(
    name="kalshi-backtest",
    help="Strategy-agnostic backtesting engine for Kalshi prediction markets.",
    no_args_is_help=True,
)
