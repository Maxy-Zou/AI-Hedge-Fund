"""Portfolio Simulator — vectorized backtest engine.

Applies a pre-built WeightFrame against a PriceFrame to produce gross and net
return series, position history, and a per-trade cost log.

Usage::

    from fund_backtest.simulator.engine import PortfolioSimulator
    from fund_backtest.config import load_cost_config

    sim = PortfolioSimulator()                        # defaults
    sim = PortfolioSimulator(load_cost_config())       # from config
    result = sim.simulate(weight_frame, price_frame)

CRITICAL: WeightFrame passed to simulate() is already shift(1)-applied by
SignalAdapter (Phase 3). Do NOT apply another shift here.
"""

from __future__ import annotations

import pandas as pd
import structlog

from fund_backtest.signal.types import WeightFrame
from fund_backtest.simulator.types import CostConfig, PortfolioResult, PriceFrame

logger = structlog.get_logger(__name__)

# Filter floating-point noise in weight changes below this threshold.
_TRADE_THRESHOLD: float = 1e-8

# Assumed trading days per calendar year for borrow cost amortisation.
_TRADING_DAYS_PER_YEAR: int = 252


class PortfolioSimulator:
    """Vectorized portfolio simulator applying cost model to weight/price frames.

    Computes daily gross returns (portfolio weighted sum of asset returns),
    transaction costs (slippage + commission on weight changes), and borrow
    costs (daily annualised rate on short positions). Returns a PortfolioResult
    with net returns, position history, and a per-trade cost log.

    All computation is vectorized (pandas operations) — no Python loops over
    dates or tickers.

    Args:
        cost_config: CostConfig with slippage, commission, and borrow cost
                     parameters. Defaults to CostConfig() if None.
    """

    def __init__(self, cost_config: CostConfig | None = None) -> None:
        """Initialise with optional cost config (defaults to CostConfig())."""
        self._config = cost_config or CostConfig()
        self._log = logger.bind(component="portfolio_simulator")

    def simulate(self, weights: WeightFrame, prices: PriceFrame) -> PortfolioResult:
        """Run a full vectorized portfolio simulation.

        # CRITICAL: WeightFrame is already shift(1)-applied from Phase 3 (SignalAdapter).
        # DO NOT apply .shift(1) here. Doing so would introduce a 2-day look-ahead lag.
        # See: Phase 3 invariant in STATE.md decisions log.

        Args:
            weights: Pre-shifted WeightFrame (date x ticker, row 0 is all-NaN).
            prices:  PriceFrame (date x ticker, adjusted close in dollars).

        Returns:
            PortfolioResult with gross_returns, net_returns, positions, trade_log.
            The leading NaN row is dropped from all return Series and positions.
        """
        self._log.info(
            "simulator_run_start",
            n_dates=len(weights),
            n_tickers=len(weights.columns),
        )

        aligned_weights, aligned_prices = self._align_frames(weights, prices)

        gross = self._compute_gross_returns(aligned_weights, aligned_prices)
        txn_cost = self._compute_transaction_costs(aligned_weights)
        borrow_cost = self._compute_borrow_costs(aligned_weights)
        net = gross - txn_cost - borrow_cost

        # Drop leading NaN row (shift artifact from Phase 3)
        valid_idx = net.dropna().index

        trade_log = self._build_trade_log(aligned_weights)

        self._log.info(
            "simulator_run_complete",
            n_trades=len(trade_log),
            date_range=(
                f"{valid_idx[0].date()} -> {valid_idx[-1].date()}" if len(valid_idx) else "empty"
            ),
        )

        return PortfolioResult(
            gross_returns=gross.loc[valid_idx],
            net_returns=net.loc[valid_idx],
            positions=aligned_weights.loc[valid_idx],
            trade_log=trade_log,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _align_frames(
        self,
        weights: WeightFrame,
        prices: PriceFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Align weights and prices to common dates and tickers.

        Logs a warning if any dates or tickers are dropped during alignment.
        Returns new DataFrames — inputs are not mutated.

        Args:
            weights: WeightFrame with DatetimeIndex and ticker columns.
            prices: PriceFrame with DatetimeIndex and ticker columns.

        Returns:
            Tuple of (aligned_weights, aligned_prices) sharing the same
            date index and column set.
        """
        common_dates = weights.index.intersection(prices.index)
        common_tickers = weights.columns.intersection(prices.columns)

        dates_dropped = len(weights.index) - len(common_dates)
        tickers_dropped = len(weights.columns) - len(common_tickers)

        if dates_dropped > 0:
            self._log.warning("simulator_dates_dropped", n=dates_dropped)
        if tickers_dropped > 0:
            self._log.warning("simulator_tickers_dropped", n=tickers_dropped)

        return (
            weights.loc[common_dates, common_tickers],
            prices.loc[common_dates, common_tickers],
        )

    def _compute_gross_returns(
        self,
        weights: pd.DataFrame,
        prices: pd.DataFrame,
    ) -> pd.Series:
        """Compute daily gross portfolio returns (vectorized, no loops).

        Formula: sum over tickers of (weight_t * daily_return_t).
        Row 0 of prices has no prior day, so pct_change() yields NaN there.
        Rows where all weights are NaN are set to NaN (shift artifact rows).

        Args:
            weights: Aligned WeightFrame.
            prices: Aligned PriceFrame.

        Returns:
            pd.Series of gross daily returns, NaN for rows with all-NaN weights.
        """
        daily_returns = prices.pct_change()
        gross_per_ticker = weights * daily_returns
        row_gross = gross_per_ticker.sum(axis=1, skipna=True)

        # Restore NaN for rows where all weights are NaN (e.g. shift artifact row)
        all_nan_mask = weights.isna().all(axis=1)
        row_gross = row_gross.where(~all_nan_mask, other=float("nan"))

        return row_gross

    def _compute_transaction_costs(self, weights: pd.DataFrame) -> pd.Series:
        """Compute per-day transaction costs from weight changes (vectorized).

        Formula: abs(weight_change) * (slippage_bps + commission_bps) / 10_000.
        First row of diff() is NaN; sum(skipna=True) treats it as 0.

        Args:
            weights: Aligned WeightFrame.

        Returns:
            pd.Series of transaction cost fractions per day.
        """
        bps_per_trade = (self._config.slippage_bps + self._config.commission_bps) / 10_000
        weight_change = weights.diff().abs()
        return (weight_change * bps_per_trade).sum(axis=1, skipna=True)

    def _compute_borrow_costs(self, weights: pd.DataFrame) -> pd.Series:
        """Compute per-day borrow costs on short positions (vectorized).

        Formula: abs(short_weight) * borrow_cost_bps_annual / 10_000 / 252.
        Long positions (weight > 0) contribute 0.

        Args:
            weights: Aligned WeightFrame.

        Returns:
            pd.Series of borrow cost fractions per day.
        """
        daily_rate = self._config.borrow_cost_bps_annual / 10_000 / _TRADING_DAYS_PER_YEAR
        short_weights = weights.clip(upper=0.0).abs()
        return (short_weights * daily_rate).sum(axis=1, skipna=True)

    def _build_trade_log(self, weights: pd.DataFrame) -> pd.DataFrame:
        """Build per-trade log from weight changes (vectorized, no loops).

        A trade is recorded when abs(weight_change) > _TRADE_THRESHOLD.
        Columns: date, ticker, weight_before, weight_after, weight_change,
                 direction, cost_fraction, cost_bps.

        Args:
            weights: Aligned WeightFrame.

        Returns:
            pd.DataFrame with one row per (date, ticker) trade event, sorted
            by date then ticker.
        """
        bps_per_trade = (self._config.slippage_bps + self._config.commission_bps) / 10_000

        # Fill NaN with 0.0 to treat entry from flat as a full trade (weight_before=0).
        # Original NaN rows represent "not yet invested"; first non-NaN row is the entry.
        w_filled = weights.fillna(0.0)

        # weight_before: prior period weight (NaN on first row; fill gives 0 there)
        weight_before = w_filled.shift(1).fillna(0.0)
        # weight_change: diff on filled frame; first row of diff stays NaN -> fill with w_filled
        weight_change = w_filled.diff().fillna(w_filled)

        mask = weight_change.abs() > _TRADE_THRESHOLD

        # Mask weight_change to non-trivial trades only, then stack to long form.
        # future_stack=True does NOT drop NaN values, so filter explicitly with dropna().
        wc_masked = weight_change.where(mask)
        long_form = (
            wc_masked.stack(future_stack=True)
            .dropna()
            .reset_index()
        )
        long_form.columns = ["date", "ticker", "weight_change"]

        if long_form.empty:
            return pd.DataFrame(
                columns=[
                    "date", "ticker", "weight_before", "weight_after",
                    "weight_change", "direction", "cost_fraction", "cost_bps",
                ]
            )

        # Add weight_before using the same trade mask
        wb_masked = weight_before.where(mask)
        wb_long = (
            wb_masked.stack(future_stack=True)
            .dropna()
            .reset_index()
        )
        wb_long.columns = ["date", "ticker", "weight_before"]
        long_form = long_form.merge(wb_long, on=["date", "ticker"], how="left")

        long_form["weight_after"] = long_form["weight_before"] + long_form["weight_change"]

        # Direction: determined by weight_after sign (new position direction)
        long_form["direction"] = long_form["weight_change"].apply(
            lambda x: "long" if x > 0 else "short"
        )

        # Cost per trade proportional to absolute weight change
        long_form["cost_fraction"] = long_form["weight_change"].abs() * bps_per_trade
        long_form["cost_bps"] = long_form["cost_fraction"] * 10_000

        return long_form.sort_values(["date", "ticker"]).reset_index(drop=True)
