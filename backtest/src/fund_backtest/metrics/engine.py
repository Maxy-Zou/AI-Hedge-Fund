"""Metrics Engine — computes institutional risk metrics from a PortfolioResult.

Provides MetricsEngine, the single entry point for transforming a
PortfolioResult (from Phase 4 simulator) into a fully-populated MetricsBundle
(consumed by Phase 6 Streamlit Dashboard and Phase 7 Tearsheet).

Usage::

    from fund_backtest.metrics.engine import MetricsEngine
    from fund_backtest.config import MetricsConfig

    engine = MetricsEngine()                        # uses MetricsConfig defaults
    engine = MetricsEngine(MetricsConfig(rolling_window=63))  # custom config
    bundle = engine.compute(portfolio_result)       # no benchmark
    bundle = engine.compute(portfolio_result, benchmark=sp500_returns)  # with benchmark

    # bundle.sharpe, bundle.max_drawdown, bundle.rolling_sharpe, etc.

CRITICAL: All annualization uses periods=252 (trading days per year).
quantstats-lumi defaults to 365 periods/year, which inflates Sharpe/Sortino by ~20%.
"""

from __future__ import annotations

import math

import pandas as pd
import quantstats_lumi as qs
import structlog

from fund_backtest.config import MetricsConfig
from fund_backtest.metrics.types import MetricsBundle
from fund_backtest.simulator.types import PortfolioResult

logger = structlog.get_logger(__name__)

# Module constant — mirrors types.py. Helpers need this without importing from
# types to avoid a circular import if types ever imports from engine.
_TRADING_DAYS_PER_YEAR: int = 252


# ---------------------------------------------------------------------------
# Private helper functions
# ---------------------------------------------------------------------------


def _rolling_drawdown(returns: pd.Series, window: int) -> pd.Series:
    """Rolling maximum drawdown over a sliding window.

    Computes the minimum (worst) drawdown within each rolling window of
    `window` trading days. Values are always <= 0 (drawdown convention is
    negative). NaN before window fills.

    Args:
        returns: Daily return Series with DatetimeIndex.
        window: Rolling window size in trading days.

    Returns:
        pd.Series of rolling min-drawdown values, aligned to returns.index.
        Values are <= 0. NaN for the first (window - 1) positions.
    """
    prices = (1 + returns).cumprod()
    drawdown = prices / prices.expanding().max() - 1
    return drawdown.rolling(window).min()


def _annual_turnover(result: PortfolioResult) -> float:
    """Annualized portfolio turnover from the simulator trade_log.

    Uses the existing weight_change column — do NOT re-diff positions, which
    would include floating-point noise and miscount partial rebalances.

    Formula: mean(daily_abs_weight_change) * 252

    Args:
        result: PortfolioResult with trade_log containing 'date' and
                'weight_change' columns.

    Returns:
        Annualized turnover as a float. 0.0 when trade_log is empty.
    """
    if result.trade_log.empty:
        return 0.0
    daily = (
        result.trade_log.groupby("date")["weight_change"]
        .apply(lambda x: x.abs().sum())
        .reindex(result.net_returns.index)
        .fillna(0.0)
    )
    return float(daily.mean() * _TRADING_DAYS_PER_YEAR)


# ---------------------------------------------------------------------------
# MetricsEngine
# ---------------------------------------------------------------------------


class MetricsEngine:
    """Computes a full institutional risk metric suite from a PortfolioResult.

    Wraps quantstats-lumi for scalar and rolling metrics, with custom helpers
    for rolling drawdown and annual turnover. All annualization uses
    periods=252 (not the quantstats default of 365).

    Args:
        config: MetricsConfig controlling rolling window, annualization period,
                and risk-free rate. Defaults to MetricsConfig() if None.
    """

    def __init__(self, config: MetricsConfig | None = None) -> None:
        """Initialise with optional MetricsConfig (defaults to MetricsConfig())."""
        self._config = config or MetricsConfig()
        self._log = logger.bind(component="metrics_engine")

    def compute(
        self,
        result: PortfolioResult,
        benchmark: pd.Series | None = None,
    ) -> MetricsBundle:
        """Compute full MetricsBundle from a PortfolioResult.

        Computes all 10 metrics across RISK-01 through RISK-04:
        - RISK-01: sharpe, sortino, calmar, max_drawdown, cagr
        - RISK-02: hit_rate, win_loss_ratio, annual_turnover
        - RISK-03: alpha, beta (0.0 when benchmark=None)
        - RISK-04: rolling_sharpe, rolling_drawdown (pd.Series)

        Args:
            result: PortfolioResult from PortfolioSimulator.simulate().
                    Must have a non-empty net_returns Series with DatetimeIndex.
            benchmark: Optional daily benchmark return Series. When provided,
                       it is reindexed to net_returns.index with fillna(0.0)
                       before computing alpha and beta. When None, alpha and
                       beta are set to 0.0 (no silent failure).

        Returns:
            Frozen MetricsBundle with all 10 fields populated.

        Raises:
            ValueError: If net_returns is empty (cannot compute any metric).
        """
        returns = result.net_returns
        rf = self._config.risk_free_rate
        periods = self._config.periods_per_year
        window = self._config.rolling_window

        self._log.info("metrics_compute_start", n_days=len(returns))

        # RISK-01: scalar risk-adjusted metrics
        # CRITICAL: periods=252, never omit or use qs default of 365.
        sharpe = float(qs.stats.sharpe(returns, rf=rf, periods=periods))
        sortino = float(qs.stats.sortino(returns, rf=rf, periods=periods))
        calmar = float(qs.stats.calmar(returns, periods=periods))
        cagr = float(qs.stats.cagr(returns, periods=periods))
        max_dd = float(qs.stats.max_drawdown(returns))  # negative float

        # RISK-02: trade metrics
        hit_rate = float(qs.stats.win_rate(returns))
        win_loss = float(qs.stats.win_loss_ratio(returns))
        # Guard: win_loss_ratio returns inf when no losing days exist
        if not math.isfinite(win_loss):
            win_loss = 0.0
        turnover = _annual_turnover(result)

        # RISK-03: benchmark comparison
        if benchmark is None:
            # Explicit 0.0 defaults — no silent failure or missing-field error
            alpha: float = 0.0
            beta: float = 0.0
        else:
            # Pre-align benchmark index to net_returns to handle date gaps
            aligned_bm = benchmark.reindex(returns.index).fillna(0.0)
            # Guard: qs.stats.greeks divides by benchmark variance (matrix[1,1]).
            # A constant or near-constant benchmark has near-zero variance, which
            # causes division-by-near-zero and produces numerically incorrect beta.
            # OLS regression is undefined when benchmark has zero variance — default to 0.0.
            bm_var = float(aligned_bm.var())
            if not math.isfinite(bm_var) or bm_var < 1e-12:
                alpha = 0.0
                beta = 0.0
            else:
                greeks = qs.stats.greeks(returns, aligned_bm, periods=float(periods))
                alpha = float(greeks["alpha"])
                beta = float(greeks["beta"])

        # RISK-04: rolling metrics
        roll_sharpe_raw = qs.stats.rolling_sharpe(
            returns,
            rf=rf,
            rolling_period=window,
            periods_per_year=periods,
        )
        # rolling_sharpe may return a DataFrame — squeeze to Series
        if isinstance(roll_sharpe_raw, pd.DataFrame):
            roll_sharpe = roll_sharpe_raw.squeeze()
        else:
            roll_sharpe = roll_sharpe_raw

        # Ensure rolling_sharpe is aligned to returns.index
        roll_sharpe = roll_sharpe.reindex(returns.index)

        roll_dd = _rolling_drawdown(returns, window)
        # Ensure rolling_drawdown is aligned to returns.index
        roll_dd = roll_dd.reindex(returns.index)

        self._log.info(
            "metrics_compute_complete",
            sharpe=round(sharpe, 4),
            max_drawdown=round(max_dd, 4),
            cagr=round(cagr, 4),
        )

        return MetricsBundle(
            sharpe=sharpe,
            sortino=sortino,
            calmar=calmar,
            max_drawdown=max_dd,
            cagr=cagr,
            hit_rate=hit_rate,
            win_loss_ratio=win_loss,
            annual_turnover=turnover,
            alpha=alpha,
            beta=beta,
            rolling_sharpe=roll_sharpe,
            rolling_drawdown=roll_dd,
        )
