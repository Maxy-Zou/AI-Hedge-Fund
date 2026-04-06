"""Tests for WalkForwardValidator — rolling expanding-window train/test splits.

RED phase: written before implementation to define the expected API and behaviour
of walkforward.py (SIM-07).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from kalshi_backtest.simulation.protocol import Position, Signal


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


def _make_backtest_result(run_id: str = "test-run"):
    """Build a minimal BacktestResult-like object for mock returns."""
    from kalshi_backtest.simulation.runner import BacktestResult

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
        daily_pnl=pd.Series([1.0, 2.0], dtype=float),
        total_pnl_cents=300,
        total_fees_cents=0,
        settled_contracts=0,
        open_contracts=0,
    )


class StubStrategy:
    def generate_signals(self, snapshot, open_positions: list[Position]) -> list[Signal]:
        return []


START_365 = datetime(2024, 1, 1)
END_365 = datetime(2024, 12, 31)  # 365 days

START_30 = datetime(2024, 1, 1)
END_30 = datetime(2024, 1, 31)   # 30 days


def _make_runner(n_calls: int):
    """Create a mock runner returning unique BacktestResult objects."""
    mock_runner = MagicMock()
    mock_runner.run.side_effect = [
        _make_backtest_result(run_id=f"run-{i}")
        for i in range(n_calls)
    ]
    return mock_runner


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWalkForwardFoldCount:
    """n_splits controls how many fold results are returned."""

    def test_fold_count_3_splits(self):
        """n_splits=3 over 365-day range must produce exactly 3 WalkForwardResult."""
        from kalshi_backtest.simulation.walkforward import WalkForwardValidator

        runner = _make_runner(n_calls=6)  # 2 runs per fold (train + test)
        validator = WalkForwardValidator(runner, n_splits=3)

        results = validator.run(
            strategy=StubStrategy(),
            start_date=START_365,
            end_date=END_365,
        )

        assert len(results) == 3

    def test_fold_count_5_splits(self):
        """Default n_splits=5 over long range produces 5 folds."""
        from kalshi_backtest.simulation.walkforward import WalkForwardValidator

        start = datetime(2022, 1, 1)
        end = datetime(2024, 1, 1)  # ~730 days
        runner = _make_runner(n_calls=10)  # 2 runs per fold
        validator = WalkForwardValidator(runner, n_splits=5)

        results = validator.run(strategy=StubStrategy(), start_date=start, end_date=end)

        assert len(results) == 5

    def test_results_list_has_n_splits_items(self):
        """len(results) == n_splits is always true."""
        from kalshi_backtest.simulation.walkforward import WalkForwardValidator

        n = 4
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)  # ~365 days → each fold ~91 days (>14)
        runner = _make_runner(n_calls=n * 2)
        validator = WalkForwardValidator(runner, n_splits=n)

        results = validator.run(strategy=StubStrategy(), start_date=start, end_date=end)

        assert len(results) == n


class TestWalkForwardDateSplits:
    """Train window always precedes test window; test windows do not overlap."""

    def test_train_window_precedes_test_window(self):
        """train_end <= test_start for every fold (no look-ahead)."""
        from kalshi_backtest.simulation.walkforward import WalkForwardValidator

        runner = _make_runner(n_calls=6)
        validator = WalkForwardValidator(runner, n_splits=3)
        results = validator.run(strategy=StubStrategy(), start_date=START_365, end_date=END_365)

        for fold in results:
            assert fold.train_end <= fold.test_start, (
                f"Look-ahead violation: train_end={fold.train_end} > test_start={fold.test_start}"
            )

    def test_fold_date_ranges_non_overlapping(self):
        """Test windows must not overlap one another."""
        from kalshi_backtest.simulation.walkforward import WalkForwardValidator

        runner = _make_runner(n_calls=6)
        validator = WalkForwardValidator(runner, n_splits=3)
        results = validator.run(strategy=StubStrategy(), start_date=START_365, end_date=END_365)

        # Sort by test_start and check each test window ends before next begins
        for i in range(len(results) - 1):
            assert results[i].test_end <= results[i + 1].test_start, (
                f"Overlap between fold {i} test_end={results[i].test_end} "
                f"and fold {i+1} test_start={results[i+1].test_start}"
            )

    def test_train_start_is_always_global_start(self):
        """Expanding window: train_start must always equal the global start_date."""
        from kalshi_backtest.simulation.walkforward import WalkForwardValidator

        runner = _make_runner(n_calls=6)
        validator = WalkForwardValidator(runner, n_splits=3)
        results = validator.run(strategy=StubStrategy(), start_date=START_365, end_date=END_365)

        for fold in results:
            assert fold.train_start == START_365


class TestWalkForwardValidation:
    """Invalid configurations raise descriptive errors."""

    def test_minimum_window_validation_too_short(self):
        """n_splits=10 over a 30-day range raises ValueError (< 14 days per fold)."""
        from kalshi_backtest.simulation.walkforward import WalkForwardValidator

        runner = MagicMock()
        validator = WalkForwardValidator(runner, n_splits=10, min_fold_days=14)

        with pytest.raises(ValueError, match="Date range too short"):
            validator.run(
                strategy=StubStrategy(),
                start_date=START_30,
                end_date=END_30,
            )

        runner.run.assert_not_called()

    def test_minimum_window_custom_min_fold_days(self):
        """Custom min_fold_days works: 30-day range with n_splits=2 and min=20 passes."""
        from kalshi_backtest.simulation.walkforward import WalkForwardValidator

        # 30 days / 2 splits = 15 days per fold → passes if min_fold_days=14
        runner = _make_runner(n_calls=4)
        validator = WalkForwardValidator(runner, n_splits=2, min_fold_days=14)

        results = validator.run(
            strategy=StubStrategy(),
            start_date=START_30,
            end_date=END_30,
        )

        assert len(results) == 2


class TestWalkForwardResultContract:
    """WalkForwardResult dataclass fields are correctly populated."""

    def test_walkforward_result_fields(self):
        """WalkForwardResult has train_start, train_end, test_start, test_end, plus results."""
        from kalshi_backtest.simulation.walkforward import WalkForwardResult, WalkForwardValidator

        runner = _make_runner(n_calls=2)
        validator = WalkForwardValidator(runner, n_splits=1)
        # Use a 30-day range with n_splits=1 — 30 days per fold, fine
        results = validator.run(
            strategy=StubStrategy(),
            start_date=START_30,
            end_date=END_30,
        )

        assert len(results) == 1
        fold = results[0]
        assert isinstance(fold, WalkForwardResult)
        assert hasattr(fold, "train_start")
        assert hasattr(fold, "train_end")
        assert hasattr(fold, "test_start")
        assert hasattr(fold, "test_end")
        assert hasattr(fold, "train_result")
        assert hasattr(fold, "test_result")

    def test_walkforward_result_is_frozen(self):
        """WalkForwardResult must be immutable (frozen dataclass)."""
        from kalshi_backtest.simulation.walkforward import WalkForwardResult, WalkForwardValidator

        runner = _make_runner(n_calls=2)
        validator = WalkForwardValidator(runner, n_splits=1)
        results = validator.run(
            strategy=StubStrategy(),
            start_date=START_30,
            end_date=END_30,
        )

        with pytest.raises((AttributeError, TypeError)):
            results[0].test_start = datetime(2099, 1, 1)  # type: ignore[misc]

    def test_runner_called_twice_per_fold(self):
        """BacktestRunner.run() must be called twice per fold (train + test)."""
        from kalshi_backtest.simulation.walkforward import WalkForwardValidator

        n_splits = 3
        mock_runner = MagicMock()
        mock_runner.run.side_effect = [
            _make_backtest_result(run_id=f"run-{i}")
            for i in range(n_splits * 2)
        ]

        validator = WalkForwardValidator(mock_runner, n_splits=n_splits)
        validator.run(strategy=StubStrategy(), start_date=START_365, end_date=END_365)

        assert mock_runner.run.call_count == n_splits * 2
