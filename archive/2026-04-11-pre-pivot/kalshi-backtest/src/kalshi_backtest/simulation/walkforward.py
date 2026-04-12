"""Expanding-window walk-forward validation to detect overfitting — SIM-07.

WalkForwardValidator splits a date range into n_splits equal test windows. For
each fold k, the training window expands from the global start to the beginning
of fold k's test window (expanding-window design). BacktestRunner.run() is called
once for the train window and once for the test window per fold.

This design confirms that out-of-sample performance holds across rolling regimes,
surfacing strategies that were tuned to a single historical period.

Usage:
    validator = WalkForwardValidator(runner, n_splits=3)
    results = validator.run(strategy, start_date, end_date)
    for fold in results:
        print(fold.test_start, fold.test_end, fold.test_result.total_pnl_cents)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog

from kalshi_backtest.simulation.protocol import Strategy
from kalshi_backtest.simulation.runner import BacktestResult, BacktestRunner

logger = structlog.get_logger(__name__).bind(component="WalkForwardValidator")


@dataclass(frozen=True)
class WalkForwardResult:
    """Immutable result for a single walk-forward fold.

    Attributes:
        train_start: Global start date (expands each fold).
        train_end:   End of the training window (= test_start).
        test_start:  Start of the out-of-sample test window.
        test_end:    End of the out-of-sample test window.
        train_result: BacktestResult for the in-sample train window.
        test_result:  BacktestResult for the out-of-sample test window.
    """

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_result: BacktestResult
    test_result: BacktestResult


class WalkForwardValidator:
    """Expanding-window walk-forward validator using BacktestRunner.

    Divides [start_date, end_date) into n_splits equal folds. For fold k:
    - Train window: [start_date, start_date + k * fold_days)
    - Test window:  [start_date + k * fold_days, start_date + (k+1) * fold_days)

    Both windows run through BacktestRunner.run() — no in-process parameter
    optimisation happens here; the caller is responsible for wiring in a strategy
    tuned on the train result.

    Args:
        runner:        An initialised BacktestRunner instance.
        n_splits:      Number of rolling test folds. Default 5.
        min_fold_days: Minimum days per fold. Raises ValueError when violated.
                       Default 14 (two full trading weeks as a sensible floor).
    """

    def __init__(
        self,
        runner: BacktestRunner,
        n_splits: int = 5,
        min_fold_days: int = 14,
    ) -> None:
        self._runner = runner
        self._n_splits = n_splits
        self._min_fold_days = min_fold_days

    def run(
        self,
        strategy: Strategy,
        start_date: datetime,
        end_date: datetime,
        series_tickers: list[str] | None = None,
    ) -> list[WalkForwardResult]:
        """Execute all walk-forward folds and return per-fold results.

        Args:
            strategy:       Strategy instance used for both train and test runs.
            start_date:     Global start of the full date range (naive UTC).
            end_date:       Global end of the full date range (naive UTC).
            series_tickers: Optional series filter passed to BacktestRunner.

        Returns:
            List of WalkForwardResult, one per fold, in chronological order.

        Raises:
            ValueError: If the date range is too short for meaningful folds
                        (fold_days < min_fold_days).
        """
        total_days = (end_date - start_date).days
        fold_days = total_days // self._n_splits

        if fold_days < self._min_fold_days:
            raise ValueError(
                f"Date range too short for {self._n_splits} splits "
                f"(min {self._min_fold_days} days per fold, got {fold_days} days)"
            )

        log = logger.bind(
            n_splits=self._n_splits,
            fold_days=fold_days,
            start_date=start_date,
            end_date=end_date,
        )
        log.info("walkforward_started")

        fold_results: list[WalkForwardResult] = []

        for k in range(self._n_splits):
            test_start = start_date + timedelta(days=k * fold_days)
            test_end = start_date + timedelta(days=(k + 1) * fold_days)
            train_end = test_start  # expanding window: train ends where test begins

            log.info(
                "walkforward_fold_started",
                fold=k,
                train_start=start_date,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )

            train_result = self._runner.run(
                strategy=strategy,
                start_date=start_date,
                end_date=train_end,
                series_tickers=series_tickers,
            )
            test_result = self._runner.run(
                strategy=strategy,
                start_date=test_start,
                end_date=test_end,
                series_tickers=series_tickers,
            )

            fold_results.append(
                WalkForwardResult(
                    train_start=start_date,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    train_result=train_result,
                    test_result=test_result,
                )
            )
            log.info(
                "walkforward_fold_complete",
                fold=k,
                train_pnl_cents=train_result.total_pnl_cents,
                test_pnl_cents=test_result.total_pnl_cents,
            )

        log.info("walkforward_finished", n_folds=len(fold_results))
        return fold_results
