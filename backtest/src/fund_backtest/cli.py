"""Typer CLI entry point for fund-backtest."""
from __future__ import annotations

import typer

app = typer.Typer(
    name="fund-backtest",
    help="Shared backtesting infrastructure for the AI Hedge Fund.",
    no_args_is_help=True,
)


if __name__ == "__main__":
    app()
