"""Unit tests for signal/validator.py and SignalAdapterConfig.

Tests for SignalValidationError, validate_signal_frame() contract enforcement,
and SignalAdapterConfig default and custom values.

TDD: These tests are written BEFORE implementation (RED phase).
"""
from __future__ import annotations

import pandas as pd
import pytest

from fund_backtest.config import SignalAdapterConfig
from fund_backtest.signal.validator import SignalValidationError, validate_signal_frame


class TestSignalValidationError:
    """Tests for SignalValidationError exception type."""

    def test_signal_validation_error_is_value_error(self) -> None:
        """SignalValidationError must be a ValueError subclass."""
        err = SignalValidationError("some message")
        assert isinstance(err, ValueError)


class TestValidateSignalFrame:
    """Tests for validate_signal_frame() contract enforcement."""

    def test_validate_signal_frame_rejects_non_datetime_index(self) -> None:
        """validate_signal_frame raises SignalValidationError for non-DatetimeIndex."""
        df = pd.DataFrame({"AAPL": [90.0]}, index=[0])  # integer index
        with pytest.raises(SignalValidationError, match="DatetimeIndex"):
            validate_signal_frame(df)

    def test_validate_signal_frame_rejects_empty_columns(self) -> None:
        """validate_signal_frame raises SignalValidationError when no columns present."""
        df = pd.DataFrame(index=pd.DatetimeIndex(["2024-01-02"]))
        with pytest.raises(SignalValidationError, match="at least one"):
            validate_signal_frame(df)

    def test_validate_signal_frame_rejects_non_string_column_names(self) -> None:
        """validate_signal_frame raises SignalValidationError for integer column names."""
        df = pd.DataFrame({1: [90.0]}, index=pd.DatetimeIndex(["2024-01-02"]))
        with pytest.raises(SignalValidationError, match="non-empty strings"):
            validate_signal_frame(df)

    def test_validate_signal_frame_rejects_empty_string_column(self) -> None:
        """validate_signal_frame raises SignalValidationError for empty string column name."""
        df = pd.DataFrame({"": [90.0]}, index=pd.DatetimeIndex(["2024-01-02"]))
        with pytest.raises(SignalValidationError, match="non-empty strings"):
            validate_signal_frame(df)

    def test_validate_signal_frame_accepts_valid_frame(self) -> None:
        """validate_signal_frame does not raise for a well-formed SignalFrame."""
        df = pd.DataFrame(
            {"AAPL": [0.8, 0.6], "MSFT": [0.3, 0.4]},
            index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"]),
        )
        # Should raise nothing
        validate_signal_frame(df)

    def test_validate_signal_frame_accepts_partial_nan(self) -> None:
        """validate_signal_frame does not raise when some values are NaN (not all-NaN)."""
        df = pd.DataFrame(
            {"AAPL": [0.8, float("nan")], "MSFT": [0.3, 0.4]},
            index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"]),
        )
        # Partial NaN is allowed — only all-NaN columns trigger a warning
        validate_signal_frame(df)

    def test_validate_signal_frame_warns_and_accepts_all_nan_column(self) -> None:
        """validate_signal_frame does not raise when a column is entirely NaN (warning only)."""
        df = pd.DataFrame(
            {"AAPL": [float("nan"), float("nan")], "MSFT": [0.3, 0.4]},
            index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"]),
        )
        # All-NaN column should log a warning but NOT raise
        validate_signal_frame(df)


class TestSignalAdapterConfig:
    """Tests for SignalAdapterConfig Pydantic model."""

    def test_signal_adapter_config_defaults(self) -> None:
        """SignalAdapterConfig() returns correct default values."""
        config = SignalAdapterConfig()
        assert config.min_coverage == 5
        assert config.gross_exposure_limit == 1.0

    def test_signal_adapter_config_custom(self) -> None:
        """SignalAdapterConfig values can be overridden on construction."""
        config = SignalAdapterConfig(min_coverage=3, gross_exposure_limit=2.0)
        assert config.min_coverage == 3
        assert config.gross_exposure_limit == 2.0
