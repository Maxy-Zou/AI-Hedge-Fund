"""Tests for ParameterSweeper — grid search over strategy parameter combinations.

RED phase: these tests are written before the implementation exists.
They define the expected API and behaviour of sweep.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from kalshi_backtest.simulation.protocol import Position, Signal


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


def _make_backtest_result(pnl_values: list[float], run_id: str = "test-run"):
    """Build a minimal BacktestResult-like mock with a daily_pnl Series."""
    from kalshi_backtest.simulation.runner import BacktestResult

    daily_pnl = pd.Series(pnl_values, dtype=float)
    trade_log = pd.DataFrame(
        columns=["ticker", "direction", "contracts", "entry_price", "entry_ts",
                 "exit_price", "exit_ts", "pnl_cents", "fee_cents", "exit_reason"]
    )
    return BacktestResult(
        run_id=run_id,
        strategy_name="StubStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        trade_log=trade_log,
        daily_pnl=daily_pnl,
        total_pnl_cents=int(sum(pnl_values)),
        total_fees_cents=0,
        settled_contracts=0,
        open_contracts=0,
    )


class StubStrategy:
    """Minimal Strategy implementation that records params it was created with."""

    def __init__(self, params: dict):
        self.params = params

    def generate_signals(self, snapshot, open_positions: list[Position]) -> list[Signal]:
        return []


START = datetime(2024, 1, 1)
END = datetime(2024, 12, 31)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParameterSweeperCombinatorics:
    """Verify that all parameter grid combinations are executed."""

    def test_sweep_runs_all_combinations(self):
        """2 params × 2 values each = 4 runs total."""
        from kalshi_backtest.simulation.sweep import ParameterSweeper

        mock_runner = MagicMock()
        mock_runner.run.side_effect = [
            _make_backtest_result([1.0, 2.0], run_id=f"run-{i}")
            for i in range(4)
        ]

        sweeper = ParameterSweeper(mock_runner)
        param_grid = {"threshold": [0.6, 0.7], "size": [10, 25]}

        results = sweeper.run(
            strategy_factory=StubStrategy,
            param_grid=param_grid,
            start_date=START,
            end_date=END,
        )

        assert mock_runner.run.call_count == 4
        assert len(results) == 4

    def test_sweep_single_param(self):
        """Single param with 3 values = 3 runs."""
        from kalshi_backtest.simulation.sweep import ParameterSweeper

        mock_runner = MagicMock()
        mock_runner.run.side_effect = [
            _make_backtest_result([float(i)], run_id=f"run-{i}")
            for i in range(3)
        ]

        sweeper = ParameterSweeper(mock_runner)
        results = sweeper.run(
            strategy_factory=StubStrategy,
            param_grid={"x": [1, 2, 3]},
            start_date=START,
            end_date=END,
        )

        assert mock_runner.run.call_count == 3
        assert len(results) == 3

    def test_empty_grid_raises(self):
        """Empty param_grid must raise ValueError immediately."""
        from kalshi_backtest.simulation.sweep import ParameterSweeper

        mock_runner = MagicMock()
        sweeper = ParameterSweeper(mock_runner)

        with pytest.raises(ValueError, match="param_grid must not be empty"):
            sweeper.run(
                strategy_factory=StubStrategy,
                param_grid={},
                start_date=START,
                end_date=END,
            )

        mock_runner.run.assert_not_called()


class TestParameterSweeperSorting:
    """Verify results are returned sorted by Sharpe descending."""

    def test_results_sorted_by_sharpe_desc(self):
        """Results at index 0 should have the highest Sharpe ratio."""
        from kalshi_backtest.simulation.sweep import ParameterSweeper

        # Construct results with clearly different Sharpe ratios
        # High Sharpe: consistent positive returns
        # Low Sharpe: volatile/negative returns
        pnl_sequences = [
            [10.0, 10.0, 10.0, 10.0],   # high sharpe (low variance)
            [1.0, -10.0, 1.0, -10.0],   # low sharpe (high variance)
        ]
        mock_runner = MagicMock()
        mock_runner.run.side_effect = [
            _make_backtest_result(pnl, run_id=f"run-{i}")
            for i, pnl in enumerate(pnl_sequences)
        ]

        sweeper = ParameterSweeper(mock_runner)
        results = sweeper.run(
            strategy_factory=StubStrategy,
            param_grid={"a": [1, 2]},
            start_date=START,
            end_date=END,
        )

        assert results[0].sharpe >= results[-1].sharpe

    def test_zero_std_gets_sharpe_zero(self):
        """A flat P&L series (std=0) should produce sharpe=0.0 without error."""
        from kalshi_backtest.simulation.sweep import ParameterSweeper, SweepResult

        mock_runner = MagicMock()
        mock_runner.run.return_value = _make_backtest_result([5.0], run_id="run-0")

        sweeper = ParameterSweeper(mock_runner)
        results = sweeper.run(
            strategy_factory=StubStrategy,
            param_grid={"x": [1]},
            start_date=START,
            end_date=END,
        )

        assert len(results) == 1
        assert results[0].sharpe == 0.0


class TestSweepResultContract:
    """Verify SweepResult dataclass fields are correctly populated."""

    def test_sweep_result_has_params(self):
        """Each SweepResult.params must contain the combo used for that run."""
        from kalshi_backtest.simulation.sweep import ParameterSweeper, SweepResult

        call_order: list[dict] = []

        def factory(params: dict):
            call_order.append(params.copy())
            return StubStrategy(params)

        mock_runner = MagicMock()
        mock_runner.run.side_effect = [
            _make_backtest_result([float(i)], run_id=f"run-{i}")
            for i in range(4)
        ]

        sweeper = ParameterSweeper(mock_runner)
        results = sweeper.run(
            strategy_factory=factory,
            param_grid={"threshold": [0.6, 0.7], "size": [10, 25]},
            start_date=START,
            end_date=END,
        )

        # Each SweepResult should have a params dict with the right keys
        for sr in results:
            assert isinstance(sr, SweepResult)
            assert "threshold" in sr.params
            assert "size" in sr.params

    def test_strategy_receives_correct_params(self):
        """strategy_factory must be called with each exact param combination."""
        from kalshi_backtest.simulation.sweep import ParameterSweeper

        received_params: list[dict] = []

        def factory(params: dict):
            received_params.append(params.copy())
            return StubStrategy(params)

        mock_runner = MagicMock()
        mock_runner.run.side_effect = [
            _make_backtest_result([1.0], run_id=f"run-{i}")
            for i in range(4)
        ]

        sweeper = ParameterSweeper(mock_runner)
        sweeper.run(
            strategy_factory=factory,
            param_grid={"a": [1, 2], "b": [10, 20]},
            start_date=START,
            end_date=END,
        )

        # 4 unique combos should have been sent
        assert len(received_params) == 4
        param_tuples = {(p["a"], p["b"]) for p in received_params}
        assert param_tuples == {(1, 10), (1, 20), (2, 10), (2, 20)}

    def test_sweep_result_is_frozen_dataclass(self):
        """SweepResult must be immutable (frozen dataclass)."""
        from kalshi_backtest.simulation.sweep import ParameterSweeper

        mock_runner = MagicMock()
        mock_runner.run.return_value = _make_backtest_result([1.0, 2.0], run_id="r0")

        sweeper = ParameterSweeper(mock_runner)
        results = sweeper.run(
            strategy_factory=StubStrategy,
            param_grid={"x": [1]},
            start_date=START,
            end_date=END,
        )

        with pytest.raises((AttributeError, TypeError)):
            results[0].sharpe = 99.0  # type: ignore[misc]
