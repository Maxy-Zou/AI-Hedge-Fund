"""Parameter grid sweep using itertools.product — no external optimization libraries.

ParameterSweeper runs BacktestRunner once per parameter combination and returns
all results sorted by Sharpe ratio descending so the best configuration is always
at index 0.

Usage:
    sweeper = ParameterSweeper(runner)
    results = sweeper.run(
        strategy_factory=MyStrategy,
        param_grid={"threshold": [0.6, 0.7], "size": [10, 25]},
        start_date=start,
        end_date=end,
    )
    best = results[0]  # highest Sharpe
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import structlog

from kalshi_backtest.simulation.protocol import Strategy
from kalshi_backtest.simulation.runner import BacktestResult, BacktestRunner

logger = structlog.get_logger(__name__).bind(component="ParameterSweeper")


@dataclass(frozen=True)
class SweepResult:
    """Immutable result for a single parameter combination in a grid sweep.

    Attributes:
        params: The exact parameter dict passed to strategy_factory for this run.
        result: The BacktestResult produced by BacktestRunner.run().
        sharpe: Annualised-ish Sharpe computed from daily_pnl (mean/std).
                Zero when std is 0 or daily_pnl has fewer than 2 observations.
    """

    params: dict[str, Any]
    result: BacktestResult
    sharpe: float


def _compute_sharpe(result: BacktestResult) -> float:
    """Compute a simple Sharpe ratio from the BacktestResult's daily_pnl.

    Returns 0.0 when the series has fewer than 2 observations or std is 0
    to avoid division-by-zero without raising.

    Args:
        result: A completed BacktestResult.

    Returns:
        Sharpe ratio as float. Higher is better.
    """
    pnl = result.daily_pnl
    if len(pnl) < 2 or pnl.std() == 0:
        return 0.0
    return float(pnl.mean() / pnl.std())


class ParameterSweeper:
    """Grid search over strategy configurations using itertools.product.

    Executes BacktestRunner once per parameter combination and returns all
    results sorted by Sharpe descending so best config is always at index 0.

    Args:
        runner: An initialised BacktestRunner instance.
    """

    def __init__(self, runner: BacktestRunner) -> None:
        self._runner = runner

    def run(
        self,
        strategy_factory: Callable[[dict[str, Any]], Strategy],
        param_grid: dict[str, list[Any]],
        start_date: datetime,
        end_date: datetime,
        series_tickers: list[str] | None = None,
    ) -> list[SweepResult]:
        """Execute all parameter combinations and return sorted results.

        Args:
            strategy_factory: Callable that accepts a params dict and returns a Strategy.
            param_grid: Mapping of parameter name → list of candidate values.
                        Must not be empty.
            start_date: Backtest window start (naive UTC).
            end_date: Backtest window end (naive UTC).
            series_tickers: Optional series filter passed through to BacktestRunner.

        Returns:
            List of SweepResult sorted by sharpe descending (best first).

        Raises:
            ValueError: If param_grid is empty.
        """
        if not param_grid:
            raise ValueError("param_grid must not be empty")

        keys = list(param_grid.keys())
        value_lists = [param_grid[k] for k in keys]
        combos = list(itertools.product(*value_lists))

        log = logger.bind(n_combinations=len(combos), start_date=start_date, end_date=end_date)
        log.info("sweep_started")

        sweep_results: list[SweepResult] = []
        for idx, combo in enumerate(combos):
            params = dict(zip(keys, combo))
            strategy = strategy_factory(params)
            backtest_result = self._runner.run(
                strategy=strategy,
                start_date=start_date,
                end_date=end_date,
                series_tickers=series_tickers,
            )
            sharpe = _compute_sharpe(backtest_result)
            sweep_results.append(SweepResult(params=params, result=backtest_result, sharpe=sharpe))
            log.info("sweep_run_complete", combo_index=idx, params=params, sharpe=sharpe)

        sweep_results.sort(key=lambda sr: sr.sharpe, reverse=True)
        log.info("sweep_finished", best_sharpe=sweep_results[0].sharpe if sweep_results else None)
        return sweep_results
