"""BacktestMetrics model and MetricsCalculator for Kalshi backtest results.

Converts a BacktestResult (raw integer cents) into a BacktestMetrics object
with standard portfolio analytics (Sharpe, Sortino, CAGR, drawdown, win rate)
computed via quantstats.

Cents-to-fraction conversion assumption:
    A $100 notional (STARTING_CAPITAL_CENTS = 10_000) is used as the base
    for converting daily P&L cents to fractional returns. This is a modelling
    choice — the engine does not track actual account equity per day, so the
    $100 denominator keeps returns in a reasonable range while remaining
    consistent across all backtest runs.
"""
from __future__ import annotations

import math
from datetime import datetime

import pandas as pd
import quantstats as qs
from pydantic import BaseModel, ConfigDict

from kalshi_backtest.simulation.runner import BacktestResult

# Module-level constant: assumed starting capital in cents ($100).
# All daily P&L cents are divided by this to produce fractional daily returns.
# This means a 100-cent profit = 1% daily return. Consistent across all runs.
STARTING_CAPITAL_CENTS = 10_000


# ---------------------------------------------------------------------------
# BacktestMetrics — frozen Pydantic output contract
# ---------------------------------------------------------------------------


class BacktestMetrics(BaseModel):
    """Immutable metrics output from a completed backtest run.

    All percentage fields are expressed as percentages (e.g. 12.5 = 12.5%),
    not decimals. max_drawdown_pct is stored as a positive number.

    Attributes:
        run_id: Unique identifier carried from the BacktestResult.
        strategy_name: Strategy class name from the BacktestResult.
        start_date: ISO-format string of the backtest start date.
        end_date: ISO-format string of the backtest end date.
        total_return_pct: Cumulative return over the run, as a percentage.
        cagr_pct: Compound annual growth rate, as a percentage.
        sharpe: Annualised Sharpe ratio (risk-free rate = 0).
        sortino: Annualised Sortino ratio.
        max_drawdown_pct: Maximum peak-to-trough drawdown as a positive percentage.
        win_rate_pct: Percentage of days with positive P&L.
        avg_trade_pnl_cents: Mean P&L per trade in cents.
        profit_factor: Gross profit divided by gross loss.
        total_trades: Total number of closed trades.
        settled_markets: Number of distinct markets that settled.
        sample_size_warning: True when settled_markets < 30 (MET-07).
        equity_curve: Cumulative dollar P&L curve, date-indexed.
        daily_returns: Fractional daily returns Series used for quantstats calls.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    run_id: str = ""
    strategy_name: str = ""
    start_date: str = ""
    end_date: str = ""
    total_return_pct: float = 0.0
    cagr_pct: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    avg_trade_pnl_cents: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    settled_markets: int = 0
    sample_size_warning: bool = False
    equity_curve: pd.Series = pd.Series(dtype=float)
    daily_returns: pd.Series = pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _to_fractional_returns(daily_pnl: pd.Series) -> pd.Series:
    """Convert a sparse integer-cents daily P&L Series to fractional returns.

    Steps:
    1. Guard: return empty float Series if input is empty.
    2. Ensure index is DatetimeIndex (convert date objects if needed).
    3. Fill gaps over the full calendar range with 0 cents.
    4. Divide by STARTING_CAPITAL_CENTS to get fractional returns.

    Args:
        daily_pnl: Sparse Series with date/datetime index and integer cents values.

    Returns:
        Dense fractional returns Series with DatetimeIndex (e.g. 0.02 = 2%).
    """
    if daily_pnl.empty:
        return pd.Series(dtype=float)

    # Convert index to DatetimeIndex if it consists of date objects
    if not isinstance(daily_pnl.index, pd.DatetimeIndex):
        daily_pnl = daily_pnl.copy()
        daily_pnl.index = pd.to_datetime(daily_pnl.index)

    full_range = pd.date_range(daily_pnl.index.min(), daily_pnl.index.max(), freq="D")
    dense = daily_pnl.reindex(full_range, fill_value=0)
    return (dense / STARTING_CAPITAL_CENTS).astype(float)


def _count_settled_markets(trade_log: pd.DataFrame) -> int:
    """Count distinct tickers where exit_reason == 'settlement'.

    Uses nunique() on the ticker column — NOT the contracts column sum.
    This correctly counts markets, not contracts.

    Args:
        trade_log: Trade log DataFrame with 'exit_reason' and 'ticker' columns.

    Returns:
        Integer count of distinct settled market tickers.
    """
    if trade_log.empty:
        return 0
    settled = trade_log[trade_log["exit_reason"] == "settlement"]
    return int(settled["ticker"].nunique())


def _build_equity_curve(daily_pnl: pd.Series) -> pd.Series:
    """Build a cumulative dollar equity curve from daily P&L in cents.

    Args:
        daily_pnl: Daily P&L Series with date/datetime index and integer cents.

    Returns:
        Cumulative sum of P&L converted to dollars, date-indexed.
    """
    if daily_pnl.empty:
        return pd.Series(dtype=float)

    if not isinstance(daily_pnl.index, pd.DatetimeIndex):
        idx = pd.to_datetime(daily_pnl.index)
        pnl = daily_pnl.copy()
        pnl.index = idx
    else:
        pnl = daily_pnl

    return (pnl / 100.0).cumsum().astype(float)


def _safe_qs(func, *args, default: float = 0.0, **kwargs) -> float:
    """Call a quantstats function, returning default on any exception or NaN.

    Args:
        func: A quantstats stats function.
        *args: Positional arguments forwarded to func.
        default: Value to return on failure (default 0.0).
        **kwargs: Keyword arguments forwarded to func.

    Returns:
        Float result from func, or default if func raises or returns NaN/inf.
    """
    try:
        result = func(*args, **kwargs)
        val = float(result)
        return val if math.isfinite(val) else default
    except Exception:
        return default


# ---------------------------------------------------------------------------
# MetricsCalculator
# ---------------------------------------------------------------------------


class MetricsCalculator:
    """Converts a BacktestResult into a BacktestMetrics object.

    Usage:
        metrics = MetricsCalculator().compute(result)

    No constructor arguments are required. All quantstats calls are wrapped in
    try/except blocks so that sparse or edge-case data never raises.
    """

    def compute(self, result: BacktestResult) -> BacktestMetrics:
        """Compute all portfolio metrics from a BacktestResult.

        Args:
            result: The completed backtest result to analyse.

        Returns:
            BacktestMetrics with all scalar and series fields populated.
            Returns zero-valued BacktestMetrics if trade_log is empty.
        """
        start_str = result.start_date.isoformat() if isinstance(result.start_date, datetime) else str(result.start_date)
        end_str = result.end_date.isoformat() if isinstance(result.end_date, datetime) else str(result.end_date)

        # --- Empty guard ---
        if result.trade_log.empty:
            return BacktestMetrics(
                run_id=result.run_id,
                strategy_name=result.strategy_name,
                start_date=start_str,
                end_date=end_str,
                total_return_pct=0.0,
                cagr_pct=0.0,
                sharpe=0.0,
                sortino=0.0,
                max_drawdown_pct=0.0,
                win_rate_pct=0.0,
                avg_trade_pnl_cents=0.0,
                profit_factor=0.0,
                total_trades=0,
                settled_markets=0,
                sample_size_warning=True,
                equity_curve=pd.Series(dtype=float),
                daily_returns=pd.Series(dtype=float),
            )

        # --- Core computations ---
        returns = _to_fractional_returns(result.daily_pnl)
        equity_curve = _build_equity_curve(result.daily_pnl)

        # total_return_pct: chain-link product of (1 + r) - 1
        if not returns.empty:
            total_return_pct = float(returns.add(1).prod() - 1) * 100
        else:
            total_return_pct = 0.0

        # quantstats metrics — all wrapped for safety
        sharpe = _safe_qs(qs.stats.sharpe, returns, periods=252)
        sortino = _safe_qs(qs.stats.sortino, returns, periods=252)
        cagr_pct = _safe_qs(qs.stats.cagr, returns, periods=252) * 100
        raw_drawdown = _safe_qs(qs.stats.max_drawdown, returns)
        max_drawdown_pct = abs(raw_drawdown) * 100  # store as positive %
        win_rate_pct = _safe_qs(qs.stats.win_rate, returns) * 100
        profit_factor = _safe_qs(qs.stats.profit_factor, returns)

        # Trade-level aggregates
        total_trades = len(result.trade_log)
        if total_trades > 0:
            avg_trade_pnl_cents = float(result.trade_log["pnl_cents"].mean())
        else:
            avg_trade_pnl_cents = 0.0

        # Sample size warning (MET-07)
        settled_markets = _count_settled_markets(result.trade_log)
        sample_size_warning = settled_markets < 30

        return BacktestMetrics(
            run_id=result.run_id,
            strategy_name=result.strategy_name,
            start_date=start_str,
            end_date=end_str,
            total_return_pct=total_return_pct,
            cagr_pct=cagr_pct,
            sharpe=sharpe,
            sortino=sortino,
            max_drawdown_pct=max_drawdown_pct,
            win_rate_pct=win_rate_pct,
            avg_trade_pnl_cents=avg_trade_pnl_cents,
            profit_factor=profit_factor,
            total_trades=total_trades,
            settled_markets=settled_markets,
            sample_size_warning=sample_size_warning,
            equity_curve=equity_curve,
            daily_returns=returns,
        )
