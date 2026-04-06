"""RED test scaffold for kalshi_backtest.metrics.dashboard.

These tests import from modules that do not yet exist. They will fail
with ImportError until Plan 02 creates kalshi_backtest/metrics/dashboard.py
and kalshi_backtest/metrics/calculator.py.

Covers requirements: MET-03 (interactive dashboard), MET-06 (category breakdown).
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

# Both imports will fail with ImportError until Plan 02 creates these modules.
from kalshi_backtest.metrics.calculator import BacktestMetrics
from kalshi_backtest.metrics.dashboard import DashboardBuilder, build_dashboard, compute_category_breakdown
from kalshi_backtest.simulation.runner import BacktestResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_trade_log() -> pd.DataFrame:
    """Trade log with KXBTC and KXETH series tickers for category breakdown tests."""
    return pd.DataFrame(
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


@pytest.fixture()
def sample_metrics() -> BacktestMetrics:
    """Minimal BacktestMetrics for dashboard construction."""
    return BacktestMetrics(
        total_return_pct=2.7,
        sharpe=1.2,
        max_drawdown_pct=-0.8,
        win_rate_pct=66.7,
        avg_trade_pnl_cents=90,
        total_trades=3,
        sample_size_warning=True,
    )


@pytest.fixture()
def minimal_backtest_result(sample_trade_log: pd.DataFrame) -> BacktestResult:
    """BacktestResult for dashboard integration tests."""
    daily_pnl = pd.Series(
        {date(2024, 1, 10): 350, date(2024, 1, 12): -80},
        dtype=int,
    )
    return BacktestResult(
        run_id="test-dash-001",
        strategy_name="TestStrategy",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        trade_log=sample_trade_log,
        daily_pnl=daily_pnl,
        total_pnl_cents=270,
        total_fees_cents=15,
        settled_contracts=3,
        open_contracts=0,
    )


# ---------------------------------------------------------------------------
# Tests — MET-03 interactive dashboard
# ---------------------------------------------------------------------------


def test_equity_curve_trace_present(
    sample_metrics: BacktestMetrics, sample_trade_log: pd.DataFrame
) -> None:
    """build_dashboard returns a plotly Figure with at least one equity curve trace."""
    import plotly.graph_objects as go

    fig = build_dashboard(sample_metrics, sample_trade_log)
    assert isinstance(fig, go.Figure), "build_dashboard must return a plotly Figure"
    trace_names = [t.name for t in fig.data]
    has_equity = any(
        name is not None and ("equity" in name.lower() or "Equity" in name)
        for name in trace_names
    )
    assert has_equity, (
        f"Figure must contain a trace named 'Equity' or similar. Found: {trace_names}"
    )


def test_write_html_creates_file(
    sample_metrics: BacktestMetrics,
    sample_trade_log: pd.DataFrame,
    tmp_path: pytest.TempPathFactory,
) -> None:
    """DashboardBuilder.write_html() creates a non-empty .html file."""
    out_path = tmp_path / "dashboard.html"
    builder = DashboardBuilder(sample_metrics, sample_trade_log)
    builder.write_html(out_path)

    assert out_path.exists(), "write_html must create the output file"
    assert out_path.suffix == ".html", "Output file must have .html extension"
    assert out_path.stat().st_size > 0, "Output HTML file must not be empty"


# ---------------------------------------------------------------------------
# Tests — MET-06 category breakdown
# ---------------------------------------------------------------------------


def test_category_breakdown_groups(sample_trade_log: pd.DataFrame) -> None:
    """compute_category_breakdown groups tickers by series prefix.

    With tickers KXBTC-A, KXBTC-B, KXETH-A:
    - Should produce a 'KXBTC' row (2 trades)
    - Should produce a 'KXETH' row (1 trade)
    """
    breakdown = compute_category_breakdown(sample_trade_log)
    assert isinstance(breakdown, pd.DataFrame), "Result must be a pandas DataFrame"
    categories = set(breakdown.index.tolist()) | set(breakdown.get("category", pd.Series()).tolist())
    assert "KXBTC" in categories or any("KXBTC" in str(c) for c in breakdown.index), (
        f"Expected KXBTC category in breakdown. Got: {breakdown}"
    )
    assert "KXETH" in categories or any("KXETH" in str(c) for c in breakdown.index), (
        f"Expected KXETH category in breakdown. Got: {breakdown}"
    )
