"""Synthetic PortfolioResult and MetricsBundle for dashboard demo mode and tests.

These factories produce realistic-looking data without requiring a database
or running the full simulation pipeline. Used by:
  - tests/unit/test_dashboard_charts.py (chart unit tests)
  - dashboard/app.py (demo mode when no DB is available)

Usage:
    from fund_backtest.dashboard.demo_data import make_demo_result, make_demo_bundle
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from fund_backtest.metrics.types import MetricsBundle
from fund_backtest.simulator.types import PortfolioResult

# Synthetic ticker universe for demo mode.
_DEMO_TICKERS: list[str] = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA"]

# Synthetic sector mapping for demo sector exposure chart (RPT-03).
DEMO_TICKER_SECTORS: dict[str, str] = {
    "AAPL": "Information Technology",
    "MSFT": "Information Technology",
    "NVDA": "Information Technology",
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
}

# Number of trading days in demo backtest (5 years).
_N_DAYS: int = 252 * 5


def make_demo_result(seed: int = 42) -> PortfolioResult:
    """Build a synthetic PortfolioResult for demo/testing.

    Generates 5 years (1260 trading days) of realistic-looking returns
    and positions for 5 tickers. No database or live data required.

    Args:
        seed: Random seed for reproducibility.

    Returns:
        PortfolioResult with DatetimeIndex starting 2021-01-04.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start="2021-01-04", periods=_N_DAYS)

    # Synthetic daily net returns: mean ~0.05% / day, std ~1%.
    net_ret_vals = rng.normal(loc=0.0005, scale=0.01, size=_N_DAYS)
    net_returns = pd.Series(net_ret_vals, index=dates, name="net_returns")

    # Gross returns slightly better than net (costs ~5bps/day average).
    gross_ret_vals = net_ret_vals + rng.uniform(0.0002, 0.0008, size=_N_DAYS)
    gross_returns = pd.Series(gross_ret_vals, index=dates, name="gross_returns")

    # Positions: 5 tickers, weights sum to ~1.0 in absolute value.
    raw_weights = rng.normal(loc=0.0, scale=0.2, size=(_N_DAYS, len(_DEMO_TICKERS)))
    # Normalise so row absolute sum <= 1.0.
    row_sums = np.abs(raw_weights).sum(axis=1, keepdims=True)
    positions_vals = raw_weights / np.where(row_sums > 1.0, row_sums, 1.0)
    positions = pd.DataFrame(positions_vals, index=dates, columns=_DEMO_TICKERS)

    # Trade log: record weight changes where abs(change) > 0.01.
    weight_diff = positions.diff().fillna(0.0)
    trade_rows: list[dict] = []
    for col in _DEMO_TICKERS:
        changes = weight_diff[col]
        for dt, chg in changes.items():
            if abs(chg) > 0.01:
                trade_rows.append({
                    "date": dt,
                    "ticker": col,
                    "direction": "short" if positions.loc[dt, col] < 0 else "long",
                    "weight_before": float(positions.loc[dt, col] - chg),
                    "weight_after": float(positions.loc[dt, col]),
                    "weight_change": float(chg),
                    "cost_fraction": 0.0015,
                    "cost_bps": 15.0,
                })
    trade_log = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame(
        columns=["date", "ticker", "direction", "weight_before",
                 "weight_after", "weight_change", "cost_fraction", "cost_bps"]
    )

    return PortfolioResult(
        gross_returns=gross_returns,
        net_returns=net_returns,
        positions=positions,
        trade_log=trade_log,
    )


def make_demo_bundle(result: PortfolioResult | None = None) -> MetricsBundle:
    """Build a synthetic MetricsBundle for demo/testing.

    Args:
        result: Optional PortfolioResult whose DatetimeIndex is used for
                rolling Series alignment. If None, calls make_demo_result().

    Returns:
        MetricsBundle with plausible synthetic scalar values and rolling Series.
    """
    if result is None:
        result = make_demo_result()

    idx = result.net_returns.index
    n = len(idx)

    # Rolling series: NaN for first 252 rows (window not yet full).
    rolling_sharpe_vals = np.full(n, np.nan)
    rolling_sharpe_vals[252:] = np.random.default_rng(0).normal(1.2, 0.3, n - 252)
    rolling_sharpe = pd.Series(rolling_sharpe_vals, index=idx, name="rolling_sharpe")

    rolling_dd_vals = np.full(n, np.nan)
    rolling_dd_vals[252:] = -np.abs(
        np.random.default_rng(1).normal(0.05, 0.03, n - 252)
    )
    rolling_drawdown = pd.Series(rolling_dd_vals, index=idx, name="rolling_drawdown")

    return MetricsBundle(
        sharpe=1.35,
        sortino=1.82,
        calmar=0.91,
        max_drawdown=-0.187,
        cagr=0.142,
        hit_rate=0.534,
        win_loss_ratio=1.27,
        annual_turnover=3.1,
        alpha=0.032,
        beta=0.74,
        rolling_sharpe=rolling_sharpe,
        rolling_drawdown=rolling_drawdown,
    )
