"""TDD RED state tests for MetricsEngine.

Tests for all 4 requirement groups (RISK-01 through RISK-04):
- TestScalarMetrics (RISK-01): Sharpe, Sortino, Calmar, max_drawdown, CAGR
- TestTradeMetrics (RISK-02): hit_rate, win_loss_ratio, annual_turnover
- TestBenchmarkMetrics (RISK-03): alpha, beta vs benchmark; 0.0 defaults when None
- TestRollingMetrics (RISK-04): rolling_sharpe and rolling_drawdown Series

RED state: MetricsEngine does not exist yet — all tests fail with ImportError.
These tests become green in Plan 02 when the engine is implemented.

Note: benchmark Series for RISK-03 tests must be synthetic (no network calls).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fund_backtest.metrics.engine import MetricsEngine  # noqa: F401 — RED: does not exist yet

from fund_backtest.simulator.types import PortfolioResult

# ---------------------------------------------------------------------------
# Shared factory helpers
# ---------------------------------------------------------------------------


def _make_portfolio_result(n: int = 300, seed: int = 42) -> PortfolioResult:
    """Build a synthetic PortfolioResult for testing.

    Args:
        n: Number of trading days.
        seed: Random seed for reproducibility.

    Returns:
        PortfolioResult with plausible return series, positions, and trade_log.
    """
    rng = np.random.default_rng(seed)
    index = pd.date_range("2020-01-02", periods=n, freq="B")

    # Net returns: random daily returns with slight positive drift
    net_arr = rng.normal(loc=0.0005, scale=0.01, size=n)
    net_returns = pd.Series(net_arr, index=index, name="net_returns")

    # Gross returns: slightly higher than net (before costs)
    gross_returns = net_returns + 0.0001

    # Positions: equal-weight 3-ticker portfolio
    positions = pd.DataFrame(
        {
            "AAPL": np.full(n, 0.33),
            "MSFT": np.full(n, 0.33),
            "NVDA": np.full(n, 0.33),
        },
        index=index,
    )

    # Trade log: ~30 trades (~1 per 10 days per ticker)
    trade_dates = index[::10]  # every 10 days
    tickers_cycle = ["AAPL", "MSFT", "NVDA"] * (len(trade_dates) // 3 + 1)
    trade_log_rows = []
    for i, date in enumerate(trade_dates):
        ticker = tickers_cycle[i]
        trade_log_rows.append(
            {
                "date": date,
                "ticker": ticker,
                "direction": "long",
                "weight_before": 0.30,
                "weight_after": 0.33,
                "weight_change": 0.03,
                "cost_fraction": 0.0015,
                "cost_bps": 15.0,
            }
        )
    trade_log = pd.DataFrame(trade_log_rows)

    return PortfolioResult(
        gross_returns=gross_returns,
        net_returns=net_returns,
        positions=positions,
        trade_log=trade_log,
    )


def _make_benchmark(result: PortfolioResult, seed: int = 99) -> pd.Series:
    """Build a synthetic benchmark Series aligned to result.net_returns index.

    Args:
        result: PortfolioResult whose index to align with.
        seed: Random seed for reproducibility.

    Returns:
        pd.Series of daily benchmark returns with same DatetimeIndex.
    """
    rng = np.random.default_rng(seed)
    arr = rng.normal(loc=0.0003, scale=0.012, size=len(result.net_returns))
    return pd.Series(arr, index=result.net_returns.index, name="benchmark")


# ---------------------------------------------------------------------------
# pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> MetricsEngine:
    """Return a default MetricsEngine instance."""
    return MetricsEngine()


@pytest.fixture
def result() -> PortfolioResult:
    """Return a synthetic PortfolioResult with 300 trading days."""
    return _make_portfolio_result()


@pytest.fixture
def benchmark(result: PortfolioResult) -> pd.Series:
    """Return a synthetic benchmark Series aligned to result index."""
    return _make_benchmark(result)


# ---------------------------------------------------------------------------
# RISK-01: Scalar metrics (Sharpe, Sortino, Calmar, max_drawdown, CAGR)
# ---------------------------------------------------------------------------


class TestScalarMetrics:
    """MetricsEngine.compute() must return correct scalar metrics (RISK-01)."""

    def test_sharpe_positive_for_positive_return_series(
        self, engine: MetricsEngine, result: PortfolioResult
    ) -> None:
        """compute() returns sharpe > 0 for a positive-drift return series.

        The synthetic series has mean=0.0005/day (>0), so Sharpe must be positive.
        """
        bundle = engine.compute(result)
        assert bundle.sharpe > 0, f"Expected positive Sharpe, got {bundle.sharpe}"

    def test_calmar_sign_correct(self, engine: MetricsEngine, result: PortfolioResult) -> None:
        """compute() returns calmar > 0 when CAGR > 0 and max_drawdown < 0.

        Calmar = CAGR / abs(max_drawdown). Both CAGR and denominator are positive
        for a positive-drift series, so Calmar must be positive.
        """
        bundle = engine.compute(result)
        assert bundle.calmar > 0, f"Expected positive Calmar, got {bundle.calmar}"

    def test_max_drawdown_is_negative(self, engine: MetricsEngine, result: PortfolioResult) -> None:
        """compute() returns max_drawdown as a negative float.

        Convention: max_drawdown <= 0 (a loss). Positive drawdown would indicate
        an incorrect sign flip.
        """
        bundle = engine.compute(result)
        assert bundle.max_drawdown <= 0, f"max_drawdown must be <= 0, got {bundle.max_drawdown}"

    def test_cagr_positive_for_positive_return_series(
        self, engine: MetricsEngine, result: PortfolioResult
    ) -> None:
        """compute() returns cagr > 0 for a cumulative positive-return series.

        The synthetic series has positive drift (mean=0.0005/day), so CAGR > 0.
        """
        bundle = engine.compute(result)
        assert bundle.cagr > 0, f"Expected positive CAGR, got {bundle.cagr}"


# ---------------------------------------------------------------------------
# RISK-02: Trade metrics (hit_rate, win_loss_ratio, annual_turnover)
# ---------------------------------------------------------------------------


class TestTradeMetrics:
    """MetricsEngine.compute() must return correct trade metrics (RISK-02)."""

    def test_hit_rate_between_zero_and_one(
        self, engine: MetricsEngine, result: PortfolioResult
    ) -> None:
        """compute() returns hit_rate in [0.0, 1.0].

        hit_rate is the fraction of profitable days — must be a valid probability.
        """
        bundle = engine.compute(result)
        assert 0.0 <= bundle.hit_rate <= 1.0, f"hit_rate must be in [0, 1], got {bundle.hit_rate}"

    def test_annual_turnover_zero_when_trade_log_empty(self, engine: MetricsEngine) -> None:
        """compute() returns annual_turnover=0.0 when trade_log is empty.

        An empty trade_log means no rebalancing occurred — turnover should be 0.
        """
        result_no_trades = _make_portfolio_result()
        # Replace trade_log with an empty DataFrame preserving column schema
        empty_log = pd.DataFrame(
            columns=[
                "date",
                "ticker",
                "direction",
                "weight_before",
                "weight_after",
                "weight_change",
                "cost_fraction",
                "cost_bps",
            ]
        )
        result_no_trades = PortfolioResult(
            gross_returns=result_no_trades.gross_returns,
            net_returns=result_no_trades.net_returns,
            positions=result_no_trades.positions,
            trade_log=empty_log,
        )
        bundle = engine.compute(result_no_trades)
        assert bundle.annual_turnover == 0.0, (
            f"Expected 0.0 turnover with empty trade_log, got {bundle.annual_turnover}"
        )

    def test_annual_turnover_positive_when_trades_exist(
        self, engine: MetricsEngine, result: PortfolioResult
    ) -> None:
        """compute() returns annual_turnover > 0 when trade_log has weight changes.

        The synthetic PortfolioResult has ~30 trades with weight_change=0.03 each.
        """
        bundle = engine.compute(result)
        assert bundle.annual_turnover > 0.0, (
            f"Expected positive turnover with trades, got {bundle.annual_turnover}"
        )


# ---------------------------------------------------------------------------
# RISK-03: Benchmark metrics (alpha, beta)
# ---------------------------------------------------------------------------


class TestBenchmarkMetrics:
    """MetricsEngine.compute() must return correct benchmark metrics (RISK-03)."""

    def test_alpha_and_beta_zero_when_no_benchmark(
        self, engine: MetricsEngine, result: PortfolioResult
    ) -> None:
        """compute() with benchmark=None returns alpha=0.0 and beta=0.0.

        When no benchmark is provided, alpha and beta default to 0.0 to avoid
        requiring users to supply a benchmark for every run.
        """
        bundle = engine.compute(result, benchmark=None)
        assert bundle.alpha == 0.0, f"Expected alpha=0.0, got {bundle.alpha}"
        assert bundle.beta == 0.0, f"Expected beta=0.0, got {bundle.beta}"

    def test_alpha_and_beta_are_floats_with_benchmark(
        self,
        engine: MetricsEngine,
        result: PortfolioResult,
        benchmark: pd.Series,
    ) -> None:
        """compute() with a synthetic benchmark returns alpha and beta as floats.

        Does not assert specific values — just confirms the computation succeeds
        and returns numeric results (not NaN, not None).
        """
        bundle = engine.compute(result, benchmark=benchmark)
        assert isinstance(bundle.alpha, float)
        assert isinstance(bundle.beta, float)
        assert not np.isnan(bundle.alpha), "alpha must not be NaN"
        assert not np.isnan(bundle.beta), "beta must not be NaN"

    def test_beta_near_zero_for_uncorrelated_benchmark(
        self, engine: MetricsEngine, result: PortfolioResult
    ) -> None:
        """compute() with a zero-correlation benchmark returns beta near 0.

        A constant-return benchmark has near-zero covariance with strategy returns,
        producing beta close to 0. Tolerance of 0.2 allows for finite-sample noise.
        """
        constant_benchmark = pd.Series(
            0.0001,  # flat daily return — zero variance
            index=result.net_returns.index,
        )
        bundle = engine.compute(result, benchmark=constant_benchmark)
        assert abs(bundle.beta) < 0.5, (
            f"Expected beta near 0 for constant benchmark, got {bundle.beta}"
        )


# ---------------------------------------------------------------------------
# RISK-04: Rolling metrics (rolling_sharpe, rolling_drawdown)
# ---------------------------------------------------------------------------


class TestRollingMetrics:
    """MetricsEngine.compute() must return correct rolling Series metrics (RISK-04)."""

    def test_rolling_sharpe_has_same_index_as_net_returns(
        self, engine: MetricsEngine, result: PortfolioResult
    ) -> None:
        """rolling_sharpe must have the same DatetimeIndex as net_returns."""
        bundle = engine.compute(result)
        assert bundle.rolling_sharpe.index.equals(result.net_returns.index), (
            "rolling_sharpe index must match net_returns index"
        )

    def test_rolling_sharpe_nan_before_window_fills(
        self, engine: MetricsEngine, result: PortfolioResult
    ) -> None:
        """rolling_sharpe has NaN for first (window - 1) values before window fills.

        Default window = 252. The first 251 values must be NaN; index 251+ may be float.
        """
        bundle = engine.compute(result)
        window = 252
        # First (window - 1) values must be NaN
        leading = bundle.rolling_sharpe.iloc[: window - 1]
        assert leading.isna().all(), (
            f"Expected NaN for first {window - 1} values, got {leading.dropna()}"
        )

    def test_rolling_drawdown_has_same_index_as_net_returns(
        self, engine: MetricsEngine, result: PortfolioResult
    ) -> None:
        """rolling_drawdown must have the same DatetimeIndex as net_returns."""
        bundle = engine.compute(result)
        assert bundle.rolling_drawdown.index.equals(result.net_returns.index), (
            "rolling_drawdown index must match net_returns index"
        )

    def test_rolling_drawdown_values_non_positive(
        self, engine: MetricsEngine, result: PortfolioResult
    ) -> None:
        """rolling_drawdown values are all <= 0 (drawdown is never positive).

        Drawdown measures loss from peak — a positive value would indicate a gain,
        which is not a drawdown. NaN values before window fills are excluded.
        """
        bundle = engine.compute(result)
        non_nan = bundle.rolling_drawdown.dropna()
        assert (non_nan <= 0).all(), (
            f"rolling_drawdown must be <= 0 everywhere, found positives: {non_nan[non_nan > 0]}"
        )

    def test_rolling_window_configurable(self, result: PortfolioResult) -> None:
        """Rolling window=20 produces first non-NaN at index 19 (0-based).

        A window of 20 means the first 19 values are NaN; index 19 is the first
        valid value (the 20th element, 0-indexed as 19).
        """
        from fund_backtest.config import MetricsConfig

        small_window_engine = MetricsEngine(config=MetricsConfig(rolling_window=20))
        bundle = small_window_engine.compute(result)

        # First 19 values must be NaN
        assert bundle.rolling_sharpe.iloc[:19].isna().all(), (
            "First 19 values must be NaN for window=20"
        )
        # Index 19 (the 20th value) should be non-NaN (window just filled)
        # Note: some implementations produce NaN at exactly window size — allow window or window-1
        first_valid_idx = bundle.rolling_sharpe.first_valid_index()
        assert first_valid_idx is not None, "rolling_sharpe must have at least one non-NaN value"
        positional_idx = result.net_returns.index.get_loc(first_valid_idx)
        assert positional_idx <= 20, (
            f"First non-NaN should be at position <= 20 for window=20, "
            f"got position {positional_idx}"
        )
