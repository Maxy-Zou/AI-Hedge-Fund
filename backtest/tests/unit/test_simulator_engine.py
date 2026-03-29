"""TDD tests for PortfolioSimulator engine behaviors.

Tests for:
- Short positions: appear in trade_log with direction="short", borrow cost deducted
- Transaction costs: charged on weight changes, zero on unchanged days
- Borrow costs: daily rate formula, zero when no shorts
- Equal-weight preservation: positions match input WeightFrame values
- Hand-calculated reference: exact net_return for a 2-ticker 3-day scenario
- No double shift: positions not shifted twice vs input WeightFrame
- Immutable inputs: WeightFrame and PriceFrame not mutated by simulate()
- NaN first row dropped: net_returns has no leading NaN

RED state: PortfolioSimulator does not exist yet — all tests fail with ImportError.
These tests become green in plan 02 when the engine is implemented.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fund_backtest.simulator.engine import PortfolioSimulator  # noqa: F401 — RED: does not exist yet
from fund_backtest.simulator.types import CostConfig, PortfolioResult


# ---------------------------------------------------------------------------
# Shared factory functions
# ---------------------------------------------------------------------------


def _make_price_frame() -> pd.DataFrame:
    """Synthetic price frame: 5 business days, 3 tickers, known returns.

    Prices designed for hand-calculation:
      Day 0: AAPL=100, NVDA=200, MSFT=50
      Day 1: AAPL=102, NVDA=198, MSFT=51  (AAPL +2%, NVDA -1%, MSFT +2%)
      Day 2: AAPL=103, NVDA=197, MSFT=52  (AAPL +0.98%, NVDA -0.51%, MSFT +1.96%)
      Day 3: AAPL=104, NVDA=198, MSFT=51  (AAPL +0.97%, NVDA +0.51%, MSFT -1.92%)
      Day 4: AAPL=105, NVDA=199, MSFT=52  (AAPL +0.96%, NVDA +0.51%, MSFT +1.96%)
    """
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    return pd.DataFrame(
        {
            "AAPL": [100.0, 102.0, 103.0, 104.0, 105.0],
            "NVDA": [200.0, 198.0, 197.0, 198.0, 199.0],
            "MSFT": [50.0, 51.0, 52.0, 51.0, 52.0],
        },
        index=dates,
    )


def _make_weight_frame(cost_config: CostConfig | None = None) -> pd.DataFrame:
    """Synthetic WeightFrame: 5 days, 3 tickers, row 0 NaN (shift artifact).

    AAPL long (+0.5), NVDA short (-0.5), MSFT flat (0.0) from day 1 onward.
    Row 0 is all-NaN to replicate the shift(1) artifact from SignalAdapter.
    """
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    data = {
        "AAPL": [float("nan"), 0.5, 0.5, 0.5, 0.5],
        "NVDA": [float("nan"), -0.5, -0.5, -0.5, -0.5],
        "MSFT": [float("nan"), 0.0, 0.0, 0.0, 0.0],
    }
    return pd.DataFrame(data, index=dates)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestShortPositions:
    """Short positions must appear in trade_log and incur borrow cost."""

    def test_short_tickers_appear_in_trade_log_with_short_direction(self) -> None:
        """NVDA (weight=-0.5) must appear in trade_log with direction='short'."""
        sim = PortfolioSimulator(CostConfig())
        result = sim.simulate(_make_weight_frame(), _make_price_frame())
        short_rows = result.trade_log[result.trade_log["direction"] == "short"]
        assert "NVDA" in short_rows["ticker"].values

    def test_borrow_cost_deducted_from_net_returns_on_short_days(self) -> None:
        """net_returns must be lower than gross_returns on days with short positions."""
        sim = PortfolioSimulator(CostConfig())
        result = sim.simulate(_make_weight_frame(), _make_price_frame())
        # On days with short positions, borrow cost causes net < gross
        diff = result.gross_returns - result.net_returns
        assert (diff >= 0).all(), "net_returns must never exceed gross_returns"
        # At least one day should have non-zero cost difference
        assert diff.sum() > 0, "expected at least some cost deduction"


class TestTransactionCosts:
    """Transaction costs charged on weight changes only."""

    def test_no_cost_when_weights_unchanged(self) -> None:
        """Days with no weight change must have zero transaction cost in trade_log.

        From day 2 onward weights are constant (0.5, -0.5, 0.0).
        Only day 1 incurs entry transaction cost.
        trade_log rows for day 3+ must have cost_bps from transaction = 0.
        """
        sim = PortfolioSimulator(CostConfig())
        result = sim.simulate(_make_weight_frame(), _make_price_frame())
        # Get trade_log for unchanged days (day index >= 2, i.e. rows 2,3,4 of weights)
        dates = _make_weight_frame().index
        unchanged_dates = dates[2:]  # days 2,3,4 have no weight change
        unchanged_rows = result.trade_log[result.trade_log["date"].isin(unchanged_dates)]
        # Transaction cost (slippage + commission) on unchanged positions should be 0
        # Rows may be absent (no trade) or present with cost_fraction from borrow only
        # The weight_change for these rows must be 0
        if len(unchanged_rows) > 0:
            assert (unchanged_rows["weight_change"].abs() < 1e-9).all()

    def test_cost_charged_proportional_to_weight_change(self) -> None:
        """A weight change of 0.5 should incur more cost than a weight change of 0.25.

        Compares two simulations: one with normal weights, one with half weights.
        The half-weight sim should have lower total transaction cost on entry day.
        """
        sim = PortfolioSimulator(CostConfig())
        # Normal weight entry
        weights_normal = _make_weight_frame()
        result_normal = sim.simulate(weights_normal, _make_price_frame())

        # Half-weight entry
        weights_half = _make_weight_frame().copy()
        weights_half.iloc[1:] = weights_half.iloc[1:] * 0.5
        result_half = sim.simulate(weights_half, _make_price_frame())

        # net_return day 1 (entry) should be closer to gross for half-weight (less cost)
        cost_normal = result_normal.gross_returns.iloc[0] - result_normal.net_returns.iloc[0]
        cost_half = result_half.gross_returns.iloc[0] - result_half.net_returns.iloc[0]
        assert cost_normal > cost_half, "larger weight change should incur more cost"


class TestBorrowCosts:
    """Borrow cost formula: abs(short_weight) * borrow_cost_bps_annual / 10000 / 252."""

    def test_daily_borrow_rate_formula(self) -> None:
        """Borrow cost on a day with NVDA weight=-0.5 must equal 0.5 * borrow / 10000 / 252.

        Uses zero transaction costs to isolate borrow cost in the net_return diff.
        """
        # Zero transaction costs to isolate borrow
        cost = CostConfig(slippage_bps=0.0, commission_bps=0.0, borrow_cost_bps_annual=50.0)
        sim = PortfolioSimulator(cost)
        result = sim.simulate(_make_weight_frame(), _make_price_frame())

        # Expected daily borrow cost for |NVDA weight| = 0.5
        expected_daily_borrow = 0.5 * (50.0 / 10_000.0 / 252.0)

        # On a no-change day (e.g. day index 1 of net_returns, which is weights[2]),
        # gross - net = borrow cost only
        gross_day = result.gross_returns.iloc[1]
        net_day = result.net_returns.iloc[1]
        actual_cost = gross_day - net_day
        assert abs(actual_cost - expected_daily_borrow) < 1e-9

    def test_zero_borrow_cost_when_no_shorts(self) -> None:
        """A long-only portfolio must have zero borrow cost.

        When all weights are non-negative, borrow cost contribution is zero.
        """
        cost = CostConfig(slippage_bps=0.0, commission_bps=0.0, borrow_cost_bps_annual=50.0)
        sim = PortfolioSimulator(cost)

        # Long-only weights
        dates = pd.date_range("2024-01-02", periods=5, freq="B")
        long_only = pd.DataFrame(
            {
                "AAPL": [float("nan"), 0.5, 0.5, 0.5, 0.5],
                "NVDA": [float("nan"), 0.5, 0.5, 0.5, 0.5],
                "MSFT": [float("nan"), 0.0, 0.0, 0.0, 0.0],
            },
            index=dates,
        )
        result = sim.simulate(long_only, _make_price_frame())

        # No shorts => gross_returns == net_returns (no borrow, no transaction after entry)
        # On unchanged days (index 1+) there is no transaction cost either
        # So diff should be zero on days 2,3,4 (indices 1,2,3 of result)
        diffs = result.gross_returns.iloc[1:] - result.net_returns.iloc[1:]
        assert (diffs.abs() < 1e-9).all()


class TestEqualWeight:
    """PortfolioResult.positions must preserve the input WeightFrame values unchanged."""

    def test_positions_preserve_input_weight_values(self) -> None:
        """result.positions must equal the non-NaN rows of the input WeightFrame."""
        sim = PortfolioSimulator(CostConfig())
        weights = _make_weight_frame()
        result = sim.simulate(weights, _make_price_frame())

        # positions should match weights[1:] (dropping the NaN first row)
        expected = weights.iloc[1:].reset_index(drop=True)
        actual = result.positions.reset_index(drop=True)
        pd.testing.assert_frame_equal(actual, expected, check_names=False)


class TestHandCalculatedReference:
    """net_return on day 2 (index 1 of result) must match hand-calculated value."""

    def test_net_return_matches_hand_calc_day2(self) -> None:
        """Verify net_return for weights[2] day using exact formula.

        Setup:
            Day 1 weights: AAPL=+0.5, NVDA=-0.5, MSFT=0.0
            Day 2 weights: same (no weight change => zero transaction cost)
            Day 2 prices: AAPL=103, NVDA=197, MSFT=52
            Day 1 prices: AAPL=102, NVDA=198, MSFT=51

        gross_return_day2:
            = 0.5 * (103/102 - 1) + (-0.5) * (197/198 - 1)
            = 0.5 * (1/102) + 0.5 * (1/198)
        borrow_cost_day2:
            = 0.5 * (50 / 10000 / 252)
        transaction_cost_day2 = 0  (no weight change)
        net_return_day2 = gross_return_day2 - borrow_cost_day2
        """
        cost = CostConfig(slippage_bps=10.0, commission_bps=5.0, borrow_cost_bps_annual=50.0)
        sim = PortfolioSimulator(cost)
        result = sim.simulate(_make_weight_frame(), _make_price_frame())

        # Hand-calculated gross return for day 2 (index 1 in result — day 2 of prices)
        gross_expected = 0.5 * (103.0 / 102.0 - 1.0) + (-0.5) * (197.0 / 198.0 - 1.0)
        # Borrow cost only (no transaction cost on unchanged day)
        borrow = 0.5 * (50.0 / 10_000.0 / 252.0)
        net_expected = gross_expected - borrow

        # result.net_returns.iloc[1] is day 2 (first non-NaN day is index 0 = entry day)
        day2_net = result.net_returns.iloc[1]
        assert abs(day2_net - net_expected) < 1e-6, (
            f"Expected net_return {net_expected:.10f}, got {day2_net:.10f}"
        )


class TestNoDoubleShift:
    """Positions must not be shifted an additional time relative to the input WeightFrame."""

    def test_positions_not_double_shifted(self) -> None:
        """result.positions must align to the same dates as input weights[1:].

        The input WeightFrame is already shifted once (shift(1) by SignalAdapter).
        The simulator must NOT apply another shift. So weights[1] (AAPL=0.5) must
        appear as positions on the same date as weights.index[1].
        """
        sim = PortfolioSimulator(CostConfig())
        weights = _make_weight_frame()
        result = sim.simulate(weights, _make_price_frame())

        # The position on the second date (index 1 of weights) must be 0.5 for AAPL
        second_date = weights.index[1]
        assert second_date in result.positions.index, (
            f"Expected date {second_date} in positions index"
        )
        assert abs(result.positions.loc[second_date, "AAPL"] - 0.5) < 1e-9


class TestImmutableInputs:
    """simulate() must not mutate the input WeightFrame or PriceFrame."""

    def test_weight_frame_not_mutated(self) -> None:
        """Input WeightFrame values must be identical before and after simulate()."""
        sim = PortfolioSimulator(CostConfig())
        weights = _make_weight_frame()
        weights_copy = weights.copy()
        sim.simulate(weights, _make_price_frame())
        pd.testing.assert_frame_equal(weights, weights_copy)

    def test_price_frame_not_mutated(self) -> None:
        """Input PriceFrame values must be identical before and after simulate()."""
        sim = PortfolioSimulator(CostConfig())
        prices = _make_price_frame()
        prices_copy = prices.copy()
        sim.simulate(_make_weight_frame(), prices)
        pd.testing.assert_frame_equal(prices, prices_copy)


class TestNaNFirstRowDropped:
    """net_returns must not contain the leading NaN row from the input WeightFrame."""

    def test_net_returns_no_leading_nan(self) -> None:
        """result.net_returns must have no NaN values — the leading NaN row is dropped."""
        sim = PortfolioSimulator(CostConfig())
        result = sim.simulate(_make_weight_frame(), _make_price_frame())
        assert not result.net_returns.isna().any(), (
            "net_returns must not contain NaN — leading NaN row should be dropped"
        )

    def test_net_returns_length_equals_non_nan_rows(self) -> None:
        """result.net_returns must have length = (len(weights) - 1), excluding NaN row."""
        sim = PortfolioSimulator(CostConfig())
        weights = _make_weight_frame()
        result = sim.simulate(weights, _make_price_frame())
        # weights has 5 rows, first is NaN => net_returns should have 4 rows
        expected_len = len(weights) - 1
        assert len(result.net_returns) == expected_len, (
            f"Expected {expected_len} rows in net_returns, got {len(result.net_returns)}"
        )
