"""RED test scaffold for kalshi_backtest.metrics.calculator.

These tests import from a module that does not yet exist. They will fail
with ImportError until Plan 02 creates kalshi_backtest/metrics/calculator.py.

Covers requirements: MET-01 (core metrics), MET-07 (sample size warning).
"""
from __future__ import annotations

import math
from datetime import date, datetime

import pandas as pd
import pytest

# This import will fail with ImportError until Plan 02 creates the module.
from kalshi_backtest.metrics.calculator import BacktestMetrics, MetricsCalculator
from kalshi_backtest.simulation.runner import BacktestResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_backtest_result() -> BacktestResult:
    """BacktestResult with 3 closed settlement trades used across most tests.

    Trades:
      - KXBTC-A: settlement, pnl_cents=200
      - KXBTC-B: settlement, pnl_cents=150
      - KXETH-A: settlement, pnl_cents=-80
    Net: 270 cents profit, 3 distinct settled tickers.
    """
    trade_log = pd.DataFrame(
        {
            "ticker": ["KXBTC-A", "KXBTC-B", "KXETH-A"],
            "direction": ["yes", "yes", "yes"],
            "contracts": [1, 1, 1],
            "entry_price": [55, 60, 70],
            "entry_ts": [
                datetime(2024, 1, 10),
                datetime(2024, 1, 11),
                datetime(2024, 1, 12),
            ],
            "exit_price": [100, 100, 0],
            "exit_ts": [
                datetime(2024, 1, 10, 16),
                datetime(2024, 1, 10, 16),
                datetime(2024, 1, 12, 16),
            ],
            "pnl_cents": [200, 150, -80],
            "fee_cents": [5, 5, 5],
            "exit_reason": ["settlement", "settlement", "settlement"],
        }
    )
    daily_pnl = pd.Series(
        {date(2024, 1, 10): 350, date(2024, 1, 12): -80},
        dtype=int,
    )
    return BacktestResult(
        run_id="test-run-001",
        strategy_name="TestStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        trade_log=trade_log,
        daily_pnl=daily_pnl,
        total_pnl_cents=270,
        total_fees_cents=15,
        settled_contracts=3,
        open_contracts=0,
    )


@pytest.fixture()
def large_backtest_result() -> BacktestResult:
    """BacktestResult with 30 distinct settled tickers — sample_size_warning should be False."""
    tickers = [f"KXBTC-{i:02d}" for i in range(30)]
    trade_log = pd.DataFrame(
        {
            "ticker": tickers,
            "direction": ["yes"] * 30,
            "contracts": [1] * 30,
            "entry_price": [50] * 30,
            "entry_ts": [datetime(2024, 1, 10)] * 30,
            "exit_price": [100] * 30,
            "exit_ts": [datetime(2024, 1, 10, 16)] * 30,
            "pnl_cents": [100] * 30,
            "fee_cents": [5] * 30,
            "exit_reason": ["settlement"] * 30,
        }
    )
    daily_pnl = pd.Series({date(2024, 1, 10): 100 * 30}, dtype=int)
    return BacktestResult(
        run_id="test-run-large",
        strategy_name="TestStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        trade_log=trade_log,
        daily_pnl=daily_pnl,
        total_pnl_cents=3000,
        total_fees_cents=150,
        settled_contracts=30,
        open_contracts=0,
    )


@pytest.fixture()
def empty_backtest_result() -> BacktestResult:
    """BacktestResult with no trades and no daily P&L entries."""
    trade_log = pd.DataFrame(
        columns=[
            "ticker",
            "direction",
            "contracts",
            "entry_price",
            "entry_ts",
            "exit_price",
            "exit_ts",
            "pnl_cents",
            "fee_cents",
            "exit_reason",
        ]
    )
    daily_pnl = pd.Series(dtype=int)
    return BacktestResult(
        run_id="test-run-empty",
        strategy_name="TestStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        trade_log=trade_log,
        daily_pnl=daily_pnl,
        total_pnl_cents=0,
        total_fees_cents=0,
        settled_contracts=0,
        open_contracts=0,
    )


# ---------------------------------------------------------------------------
# Tests — MET-01 core metrics
# ---------------------------------------------------------------------------


def test_sharpe_is_finite(minimal_backtest_result: BacktestResult) -> None:
    """compute() returns BacktestMetrics with a finite Sharpe ratio."""
    metrics = MetricsCalculator().compute(minimal_backtest_result)
    assert isinstance(metrics, BacktestMetrics)
    assert math.isfinite(metrics.sharpe)


def test_total_return_positive(minimal_backtest_result: BacktestResult) -> None:
    """total_return_pct is positive for a net-profitable result."""
    metrics = MetricsCalculator().compute(minimal_backtest_result)
    assert metrics.total_return_pct > 0


def test_win_rate_range(minimal_backtest_result: BacktestResult) -> None:
    """win_rate_pct is in [0, 100] for any valid result."""
    metrics = MetricsCalculator().compute(minimal_backtest_result)
    assert 0.0 <= metrics.win_rate_pct <= 100.0


# ---------------------------------------------------------------------------
# Tests — MET-07 sample size warning
# ---------------------------------------------------------------------------


def test_sample_warning_true_when_few(minimal_backtest_result: BacktestResult) -> None:
    """sample_size_warning is True when fewer than 30 distinct settled tickers."""
    metrics = MetricsCalculator().compute(minimal_backtest_result)
    assert metrics.sample_size_warning is True


def test_sample_warning_false_when_enough(large_backtest_result: BacktestResult) -> None:
    """sample_size_warning is False when >= 30 distinct settled tickers."""
    metrics = MetricsCalculator().compute(large_backtest_result)
    assert metrics.sample_size_warning is False


# ---------------------------------------------------------------------------
# Tests — empty result guard
# ---------------------------------------------------------------------------


def test_empty_result_no_error(empty_backtest_result: BacktestResult) -> None:
    """compute() on empty trade_log returns BacktestMetrics without raising.

    total_return_pct must be 0.0 and sample_size_warning must be True.
    """
    metrics = MetricsCalculator().compute(empty_backtest_result)
    assert isinstance(metrics, BacktestMetrics)
    assert metrics.total_return_pct == 0.0
    assert metrics.sample_size_warning is True


# ---------------------------------------------------------------------------
# Tests — MET-04 Brier score
# ---------------------------------------------------------------------------
# These tests will fail RED until Plan 04-03 adds brier_score to BacktestMetrics
# and the corresponding computation to MetricsCalculator.compute().
# ---------------------------------------------------------------------------


@pytest.fixture()
def brier_trade_log_yes_settlement() -> BacktestResult:
    """BacktestResult with one settled YES trade at 60 cents.

    Entry price 60 cents = 0.6 probability. Settlement at YES (exit=100).
    Brier score = (0.6 - 1.0)^2 = 0.16
    """
    trade_log = pd.DataFrame(
        {
            "ticker": ["KXBTC-A"],
            "direction": ["yes"],
            "contracts": [1],
            "entry_price": [60],
            "entry_ts": [datetime(2024, 1, 10)],
            "exit_price": [100],
            "exit_ts": [datetime(2024, 1, 10, 16)],
            "pnl_cents": [400],
            "fee_cents": [5],
            "exit_reason": ["settlement"],
        }
    )
    daily_pnl = pd.Series({date(2024, 1, 10): 400}, dtype=int)
    return BacktestResult(
        run_id="brier-yes-001",
        strategy_name="TestStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        trade_log=trade_log,
        daily_pnl=daily_pnl,
        total_pnl_cents=400,
        total_fees_cents=5,
        settled_contracts=1,
        open_contracts=0,
    )


@pytest.fixture()
def brier_trade_log_no_settlement() -> BacktestResult:
    """BacktestResult with one settled NO trade at 40 cents.

    Entry price 40 cents on NO side. Implied YES probability = 1 - 0.40 = 0.60.
    Settlement at NO (exit=0 from YES perspective, meaning NO settled correctly).
    Brier score for NO trade: (0.60 - 1.0)^2 = 0.16
    """
    trade_log = pd.DataFrame(
        {
            "ticker": ["KXBTC-B"],
            "direction": ["no"],
            "contracts": [1],
            "entry_price": [40],
            "entry_ts": [datetime(2024, 1, 11)],
            "exit_price": [0],
            "exit_ts": [datetime(2024, 1, 11, 16)],
            "pnl_cents": [600],
            "fee_cents": [5],
            "exit_reason": ["settlement"],
        }
    )
    daily_pnl = pd.Series({date(2024, 1, 11): 600}, dtype=int)
    return BacktestResult(
        run_id="brier-no-001",
        strategy_name="TestStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        trade_log=trade_log,
        daily_pnl=daily_pnl,
        total_pnl_cents=600,
        total_fees_cents=5,
        settled_contracts=1,
        open_contracts=0,
    )


@pytest.fixture()
def brier_trade_log_mtm_only() -> BacktestResult:
    """BacktestResult with only mark-to-market exits (no settlements).

    brier_score must be None — cannot compute without settled trades.
    """
    trade_log = pd.DataFrame(
        {
            "ticker": ["KXBTC-C"],
            "direction": ["yes"],
            "contracts": [1],
            "entry_price": [50],
            "entry_ts": [datetime(2024, 1, 12)],
            "exit_price": [55],
            "exit_ts": [datetime(2024, 1, 12, 16)],
            "pnl_cents": [50],
            "fee_cents": [5],
            "exit_reason": ["mark-to-market"],
        }
    )
    daily_pnl = pd.Series({date(2024, 1, 12): 50}, dtype=int)
    return BacktestResult(
        run_id="brier-mtm-001",
        strategy_name="TestStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        trade_log=trade_log,
        daily_pnl=daily_pnl,
        total_pnl_cents=50,
        total_fees_cents=5,
        settled_contracts=0,
        open_contracts=0,
    )


@pytest.fixture()
def brier_trade_log_mixed() -> BacktestResult:
    """BacktestResult mixing settlement and mark-to-market rows.

    Only settlement rows should contribute to the Brier score computation.
    """
    trade_log = pd.DataFrame(
        {
            "ticker": ["KXBTC-D", "KXBTC-E"],
            "direction": ["yes", "yes"],
            "contracts": [1, 1],
            "entry_price": [60, 50],
            "entry_ts": [datetime(2024, 1, 13), datetime(2024, 1, 13)],
            "exit_price": [100, 55],
            "exit_ts": [datetime(2024, 1, 13, 16), datetime(2024, 1, 13, 16)],
            "pnl_cents": [400, 50],
            "fee_cents": [5, 5],
            "exit_reason": ["settlement", "mark-to-market"],
        }
    )
    daily_pnl = pd.Series({date(2024, 1, 13): 450}, dtype=int)
    return BacktestResult(
        run_id="brier-mixed-001",
        strategy_name="TestStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        trade_log=trade_log,
        daily_pnl=daily_pnl,
        total_pnl_cents=450,
        total_fees_cents=10,
        settled_contracts=1,
        open_contracts=0,
    )


def test_brier_score_yes_settlement(brier_trade_log_yes_settlement: BacktestResult) -> None:
    """MET-04: YES trade at 60 cents settling YES → brier_score ≈ 0.16.

    Probability implied by entry: 60/100 = 0.60.
    Outcome: YES settled = 1.0.
    Brier = (0.60 - 1.0)^2 = 0.16
    """
    metrics = MetricsCalculator().compute(brier_trade_log_yes_settlement)
    # brier_score attribute will fail RED until Plan 04-03 adds it to BacktestMetrics
    assert metrics.brier_score is not None
    assert abs(metrics.brier_score - 0.16) < 1e-6


def test_brier_score_no_settlement(brier_trade_log_no_settlement: BacktestResult) -> None:
    """MET-04: NO trade at 40 cents settling NO → brier_score ≈ 0.16.

    Entry price 40 on NO side → implied YES probability = 1 - 0.40 = 0.60.
    NO settled means YES outcome = 0.0.
    Brier = (0.60 - 0.0)^2 = 0.36... wait — that's the YES side.
    For a NO trade: predicted NO probability = 1 - entry/100 = 0.60.
    Actual NO outcome = 1.0 (NO settled).
    Brier = (0.60 - 1.0)^2 = 0.16
    """
    metrics = MetricsCalculator().compute(brier_trade_log_no_settlement)
    assert metrics.brier_score is not None
    assert abs(metrics.brier_score - 0.16) < 1e-6


def test_brier_score_none_when_no_settlement(brier_trade_log_mtm_only: BacktestResult) -> None:
    """MET-04: All exit_reason='mark-to-market' → brier_score is None."""
    metrics = MetricsCalculator().compute(brier_trade_log_mtm_only)
    assert metrics.brier_score is None


def test_brier_score_excludes_mtm(brier_trade_log_mixed: BacktestResult) -> None:
    """MET-04: Mixed settlement and mark-to-market → only settlement rows counted.

    The mark-to-market row (KXBTC-E at 50 cents) must not contribute.
    Only KXBTC-D (YES at 60 cents, settled YES) contributes → brier_score ≈ 0.16.
    """
    metrics = MetricsCalculator().compute(brier_trade_log_mixed)
    assert metrics.brier_score is not None
    assert abs(metrics.brier_score - 0.16) < 1e-6
