"""RED test scaffold for kalshi_backtest.metrics.trade_log.

These tests import from a module that does not yet exist. They will fail
with ImportError until Plan 02 creates kalshi_backtest/metrics/trade_log.py.

Covers requirement: MET-02 (CSV trade log export with dollar columns).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

# This import will fail with ImportError until Plan 02 creates the module.
from kalshi_backtest.metrics.trade_log import export_trade_log
from kalshi_backtest.simulation.runner import BacktestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trade_log() -> pd.DataFrame:
    """Return a minimal 3-row trade log DataFrame."""
    return pd.DataFrame(
        {
            "ticker": ["KXBTC-A", "KXBTC-B", "KXETH-A"],
            "direction": ["yes", "yes", "no"],
            "contracts": [1, 2, 1],
            "entry_price": [55, 60, 30],
            "entry_ts": [
                datetime(2024, 1, 10),
                datetime(2024, 1, 11),
                datetime(2024, 1, 12),
            ],
            "exit_price": [100, 100, 0],
            "exit_ts": [
                datetime(2024, 1, 10, 16),
                datetime(2024, 1, 10, 16),
                datetime(2024, 1, 12, 16),
            ],
            "pnl_cents": [200, 300, -80],
            "fee_cents": [5, 10, 5],
            "exit_reason": ["settlement", "settlement", "settlement"],
        }
    )


def _make_backtest_result(trade_log: pd.DataFrame) -> BacktestResult:
    """Wrap a trade_log DataFrame in a minimal BacktestResult."""
    import pandas as pd
    from datetime import date

    daily_pnl = pd.Series(dtype=int)
    return BacktestResult(
        run_id="test-export-001",
        strategy_name="TestStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        trade_log=trade_log,
        daily_pnl=daily_pnl,
        total_pnl_cents=int(trade_log["pnl_cents"].sum()) if len(trade_log) > 0 else 0,
        total_fees_cents=int(trade_log["fee_cents"].sum()) if len(trade_log) > 0 else 0,
        settled_contracts=len(trade_log),
        open_contracts=0,
    )


# ---------------------------------------------------------------------------
# Tests — MET-02 CSV export
# ---------------------------------------------------------------------------


def test_export_columns(tmp_path: pytest.TempPathFactory) -> None:
    """Exported CSV must include both raw cents columns and dollar conversion columns."""
    trade_log = _make_trade_log()
    result = _make_backtest_result(trade_log)
    out_path = tmp_path / "trades.csv"

    export_trade_log(result, out_path)

    assert out_path.exists(), "export_trade_log should create the output file"
    df = pd.read_csv(out_path)
    required_columns = {"ticker", "direction", "entry_ts", "exit_ts", "pnl_usd", "fee_usd"}
    missing = required_columns - set(df.columns)
    assert not missing, f"Missing columns in exported CSV: {missing}"


def test_dollar_conversion(tmp_path: pytest.TempPathFactory) -> None:
    """pnl_usd and fee_usd must equal pnl_cents / 100 and fee_cents / 100 respectively."""
    trade_log = _make_trade_log()
    result = _make_backtest_result(trade_log)
    out_path = tmp_path / "trades.csv"

    export_trade_log(result, out_path)

    df = pd.read_csv(out_path)
    # Reload source trade_log for comparison
    expected_pnl_usd = trade_log["pnl_cents"] / 100
    expected_fee_usd = trade_log["fee_cents"] / 100
    for i, (expected_pnl, expected_fee) in enumerate(
        zip(expected_pnl_usd, expected_fee_usd, strict=True)
    ):
        assert abs(df.loc[i, "pnl_usd"] - expected_pnl) < 1e-9, (
            f"Row {i}: pnl_usd {df.loc[i, 'pnl_usd']} != {expected_pnl}"
        )
        assert abs(df.loc[i, "fee_usd"] - expected_fee) < 1e-9, (
            f"Row {i}: fee_usd {df.loc[i, 'fee_usd']} != {expected_fee}"
        )


def test_empty_trade_log_no_file(tmp_path: pytest.TempPathFactory) -> None:
    """export_trade_log with empty trade_log does not create the file (or creates it empty)."""
    empty_trade_log = pd.DataFrame(
        columns=[
            "ticker",
            "direction",
            "contracts",
            "entry_price",
            "entry_ts",
            "exit_price",
            "exit_ts",
            "pnl_cents",
            "fee_cents",
            "exit_reason",
        ]
    )
    result = _make_backtest_result(empty_trade_log)
    out_path = tmp_path / "empty_trades.csv"

    export_trade_log(result, out_path)

    # Either the file does not exist, or it exists but has no data rows
    if out_path.exists():
        df = pd.read_csv(out_path)
        assert len(df) == 0, "Empty trade log export must produce a file with zero data rows"
