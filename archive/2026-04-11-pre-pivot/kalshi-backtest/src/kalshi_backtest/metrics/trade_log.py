"""CSV trade log export for Kalshi backtest results.

Writes the trade log from a BacktestResult to a CSV file, adding dollar-
converted columns alongside the raw cents columns.

Convention:
    - entry_price and exit_price remain in cents [0–100] — these are Kalshi
      prediction market prices, not dollar amounts.
    - pnl_cents and fee_cents stay in the output (raw) AND are also provided
      as pnl_usd and fee_usd (divided by 100) for human readability.

The input DataFrame is never mutated — a copy is made before adding columns.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from kalshi_backtest.simulation.runner import BacktestResult


def export_trade_log(result: BacktestResult, output_path: str | Path) -> None:
    """Write the trade log from a BacktestResult to a CSV file.

    Adds pnl_usd and fee_usd columns (cents / 100) to the output CSV.
    Does nothing if the trade log is empty.

    Args:
        result: Completed BacktestResult containing the trade log DataFrame.
        output_path: Destination path for the CSV file.

    Returns:
        None. Writes file to output_path if trade_log is non-empty.

    Raises:
        OSError: If the output path cannot be written (propagated from to_csv).
    """
    trade_log = result.trade_log

    # Guard: do not write a file for empty trade logs
    if trade_log.empty:
        return

    # Build a copy to avoid mutating the immutable BacktestResult's DataFrame
    df = trade_log.copy()

    # Add dollar-converted columns (round to 2 decimal places for clean CSV output)
    df["pnl_usd"] = (df["pnl_cents"] / 100).round(2)
    df["fee_usd"] = (df["fee_cents"] / 100).round(2)

    df.to_csv(output_path, index=False)
