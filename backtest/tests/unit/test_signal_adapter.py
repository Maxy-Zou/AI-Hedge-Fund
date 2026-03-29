"""Unit tests for signal/adapter.py SignalAdapter behavioral contracts.

Tests for:
- SignalAdapter.adapt() return type and value range
- Look-ahead bias guard (shift(1) behavior)
- min_coverage zeroing
- All-NaN column dropping
- Invalid input raises SignalValidationError
- Immutability (input not mutated)
- Gross exposure scaling

TDD: These tests are written BEFORE implementation (RED phase).
"""
from __future__ import annotations

import pandas as pd
import pytest

from fund_backtest.config import SignalAdapterConfig
from fund_backtest.signal.adapter import SignalAdapter
from fund_backtest.signal.validator import SignalValidationError


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

def _make_signal_frame() -> pd.DataFrame:
    """Build a 5-row, 4-ticker SignalFrame for adapter tests.

    AAPL has a spike (99.0) on index 2 — used to verify look-ahead bias guard.
    NVDA has the inverse (1.0) on the same date.
    """
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    return pd.DataFrame(
        {
            "AAPL": [10.0, 20.0, 99.0, 30.0, 40.0],  # spike on index 2
            "NVDA": [90.0, 80.0,  1.0, 70.0, 60.0],
            "MSFT": [50.0, 50.0, 50.0, 50.0, 50.0],
            "GOOG": [25.0, 25.0, 25.0, 25.0, 25.0],
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSignalAdapterReturnType:
    """adapt() must return a pandas DataFrame."""

    def test_adapt_returns_dataframe(self) -> None:
        """SignalAdapter.adapt() returns a pd.DataFrame."""
        df = _make_signal_frame()
        # Use min_coverage=1 so no rows are zeroed — isolates return-type check
        config = SignalAdapterConfig(min_coverage=1)
        result = SignalAdapter(config).adapt(df)
        assert isinstance(result, pd.DataFrame)


class TestSignalAdapterWeightRange:
    """Weights must be in [-1.0, +1.0] after normalization."""

    def test_weight_values_in_minus_one_to_one(self) -> None:
        """All non-NaN weight values must satisfy |w| <= 1.0."""
        df = _make_signal_frame()
        # Use min_coverage=1 so rows are not zeroed — isolates weight range check
        config = SignalAdapterConfig(min_coverage=1)
        result = SignalAdapter(config).adapt(df)
        max_abs = result.stack().dropna().abs().max()
        assert max_abs <= 1.0 + 1e-9


class TestSignalAdapterLookAheadBiasGuard:
    """shift(1) ensures signal on date T is reflected at T+1, not T."""

    def test_look_ahead_bias_guard(self) -> None:
        """Spike on date T must produce shifted weights — visible only at T+1.

        On the spike day (index 2): AAPL=99, NVDA=1.
        shift(1) means weights on day 2 are derived from day 1 signals:
          AAPL=20, NVDA=80 => NVDA outranks AAPL on day 2.
        On day 3 (T+1): the spike is reflected => AAPL outranks NVDA.

        Uses min_coverage=1 to prevent all rows from being zeroed
        (fixture has 4 tickers; default min_coverage=5 would zero all rows).
        """
        df = _make_signal_frame()
        # min_coverage=1 isolates the shift behavior from coverage logic
        config = SignalAdapterConfig(min_coverage=1)
        result = SignalAdapter(config).adapt(df)

        spike_day = 2  # index 2 has AAPL=99, NVDA=1

        # On spike day itself: weights from T-1 signal => NVDA > AAPL
        assert result.iloc[spike_day]["NVDA"] > result.iloc[spike_day]["AAPL"]

        # On T+1: spike is now visible => AAPL > NVDA
        assert result.iloc[spike_day + 1]["AAPL"] > result.iloc[spike_day + 1]["NVDA"]

    def test_first_row_is_nan_after_shift(self) -> None:
        """First row of WeightFrame must be all-NaN (shift(1) artifact)."""
        df = _make_signal_frame()
        # min_coverage=1 prevents all-zero rows from masking the NaN behavior
        config = SignalAdapterConfig(min_coverage=1)
        result = SignalAdapter(config).adapt(df)
        assert result.iloc[0].isna().all()


class TestSignalAdapterMinCoverage:
    """Rows with too few non-NaN tickers should be zeroed out."""

    def test_low_coverage_row_is_zeroed(self) -> None:
        """All rows zeroed when min_coverage exceeds available tickers."""
        df = _make_signal_frame()
        config = SignalAdapterConfig(min_coverage=10)  # impossible to meet with 4 tickers
        result = SignalAdapter(config).adapt(df)
        # All non-NaN weights should be zero (coverage threshold never met)
        assert (result.fillna(0).abs().sum(axis=1) == 0).all()


class TestSignalAdapterNaNColumnDropping:
    """All-NaN columns must be silently dropped from the output."""

    def test_all_nan_column_dropped_silently(self) -> None:
        """An all-NaN column is dropped from the WeightFrame output."""
        df = _make_signal_frame()
        df_with_nan_col = df.copy()
        df_with_nan_col["DEAD"] = float("nan")
        result = SignalAdapter().adapt(df_with_nan_col)
        assert "DEAD" not in result.columns


class TestSignalAdapterValidation:
    """Invalid SignalFrame inputs must raise SignalValidationError."""

    def test_invalid_input_raises_validation_error(self) -> None:
        """adapt() raises SignalValidationError for a non-DatetimeIndex frame."""
        bad_df = pd.DataFrame({"AAPL": [90.0]}, index=[0])  # integer index
        with pytest.raises(SignalValidationError):
            SignalAdapter().adapt(bad_df)


class TestSignalAdapterImmutability:
    """Input SignalFrame must never be mutated by adapt()."""

    def test_input_not_mutated(self) -> None:
        """adapt() must not modify the input DataFrame in place."""
        df = _make_signal_frame()
        original = df.copy()
        SignalAdapter().adapt(df)
        pd.testing.assert_frame_equal(df, original)


class TestSignalAdapterGrossExposure:
    """Gross exposure scaling must cap absolute weight sums per row."""

    def test_gross_exposure_scaling(self) -> None:
        """Rows where abs(weight sum) > gross_exposure_limit are scaled down."""
        df = _make_signal_frame()
        config = SignalAdapterConfig(gross_exposure_limit=0.5)
        result = SignalAdapter(config).adapt(df)
        row_abs_sums = result.fillna(0).abs().sum(axis=1)
        assert (row_abs_sums <= 0.5 + 1e-9).all()
