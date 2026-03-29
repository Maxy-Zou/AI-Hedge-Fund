"""TDD tests for MetricsBundle type contract.

Tests for:
- MetricsBundle construction with all required fields (scalar + rolling pd.Series)
- MetricsBundle frozen invariant (mutation raises exception)
- Field types: floats for scalars, pd.Series for rolling metrics
- max_drawdown convention: accepts negative float (convention is negative)

These tests should PASS after Plan 01 Task 1 (types.py already created).
No MetricsEngine import — purely tests the type contract.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fund_backtest.metrics.types import MetricsBundle

# ---------------------------------------------------------------------------
# Shared factory helper
# ---------------------------------------------------------------------------


def _make_bundle(n: int = 30) -> MetricsBundle:
    """Construct a valid MetricsBundle with synthetic pd.Series rolling fields.

    Args:
        n: Number of rows in the rolling Series (trading days).

    Returns:
        A fully populated MetricsBundle with representative values.
    """
    idx = pd.date_range("2020-01-02", periods=n, freq="B")
    return MetricsBundle(
        sharpe=1.2,
        sortino=1.5,
        calmar=0.8,
        max_drawdown=-0.15,
        cagr=0.12,
        hit_rate=0.54,
        win_loss_ratio=1.3,
        annual_turnover=2.5,
        alpha=0.02,
        beta=0.95,
        rolling_sharpe=pd.Series(np.nan, index=idx),
        rolling_drawdown=pd.Series(np.nan, index=idx),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMetricsBundle:
    """MetricsBundle schema, construction, and immutability invariants."""

    def test_construction_with_all_fields(self) -> None:
        """MetricsBundle can be constructed with all required fields including pd.Series."""
        bundle = _make_bundle()
        assert bundle.sharpe == 1.2
        assert bundle.sortino == 1.5
        assert bundle.calmar == 0.8
        assert bundle.max_drawdown == -0.15
        assert bundle.cagr == 0.12
        assert bundle.hit_rate == 0.54
        assert bundle.win_loss_ratio == 1.3
        assert bundle.annual_turnover == 2.5
        assert bundle.alpha == 0.02
        assert bundle.beta == 0.95
        assert isinstance(bundle.rolling_sharpe, pd.Series)
        assert isinstance(bundle.rolling_drawdown, pd.Series)

    def test_frozen_mutation_raises(self) -> None:
        """MetricsBundle.sharpe = 9.9 must raise — frozen invariant enforced."""
        from pydantic import ValidationError

        bundle = _make_bundle()
        with pytest.raises((ValidationError, TypeError)):
            bundle.sharpe = 9.9  # type: ignore[misc]

    def test_field_types(self) -> None:
        """Scalar fields must be float; rolling fields must be pd.Series."""
        bundle = _make_bundle()
        assert isinstance(bundle.sharpe, float)
        assert isinstance(bundle.sortino, float)
        assert isinstance(bundle.calmar, float)
        assert isinstance(bundle.max_drawdown, float)
        assert isinstance(bundle.cagr, float)
        assert isinstance(bundle.hit_rate, float)
        assert isinstance(bundle.win_loss_ratio, float)
        assert isinstance(bundle.annual_turnover, float)
        assert isinstance(bundle.alpha, float)
        assert isinstance(bundle.beta, float)
        assert isinstance(bundle.rolling_sharpe, pd.Series)
        assert isinstance(bundle.rolling_drawdown, pd.Series)

    def test_max_drawdown_accepts_negative_float(self) -> None:
        """max_drawdown field accepts negative float — convention is negative (e.g. -0.25).

        The negative convention matches quantstats-lumi output (Pitfall 3 in RESEARCH.md).
        Do not flip the sign at storage time — let the display layer render it as "25%".
        """
        bundle = _make_bundle()
        assert bundle.max_drawdown == -0.15
        assert bundle.max_drawdown < 0, "max_drawdown must be negative by convention"

        # Also verify that a larger drawdown is still accepted as a negative float
        idx = pd.date_range("2020-01-02", periods=5, freq="B")
        deep_dd_bundle = MetricsBundle(
            sharpe=0.5,
            sortino=0.7,
            calmar=0.2,
            max_drawdown=-0.45,  # 45% drawdown
            cagr=0.09,
            hit_rate=0.50,
            win_loss_ratio=1.0,
            annual_turnover=1.0,
            alpha=0.0,
            beta=1.0,
            rolling_sharpe=pd.Series(np.nan, index=idx),
            rolling_drawdown=pd.Series(np.nan, index=idx),
        )
        assert deep_dd_bundle.max_drawdown == -0.45
