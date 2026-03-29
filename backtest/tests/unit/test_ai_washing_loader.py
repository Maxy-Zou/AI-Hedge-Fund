"""Unit tests for signal/loaders/ai_washing.py AiWashingLoader behavioral contracts.

Tests cover all INT-02 behaviors using mocked SQLAlchemy sessions.
No real DB connections are made — all session.execute() calls are mocked.

TDD: These tests are written BEFORE implementation (RED phase).
"""
from __future__ import annotations

import pytest
from datetime import date
from unittest.mock import MagicMock

import sqlalchemy.exc

from fund_backtest.signal.loaders import AiWashingLoader, SignalLoadError


# ---------------------------------------------------------------------------
# Shared mock session helper
# ---------------------------------------------------------------------------


def _make_session(rows: list[tuple]) -> MagicMock:
    """Build a mock SQLAlchemy session whose execute() returns given rows.

    Args:
        rows: List of (ticker, signal_date, composite_score) tuples.

    Returns:
        MagicMock session with execute().fetchall() returning rows.
    """
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    session.execute.return_value = mock_result
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAiWashingLoaderHappyPath:
    """AiWashingLoader.load() returns a valid SignalFrame on success."""

    def test_load_returns_signal_frame(self) -> None:
        """load() returns DataFrame with DatetimeIndex, str columns, float values."""
        import pandas as pd

        rows = [
            ("AAPL", date(2024, 1, 2), 75),
            ("MSFT", date(2024, 1, 2), 60),
            ("AAPL", date(2024, 1, 3), 80),
        ]
        session = _make_session(rows)
        loader = AiWashingLoader(session)
        result = loader.load()

        # Shape: 2 dates x 2 tickers
        assert result.shape == (2, 2), f"Expected (2, 2), got {result.shape}"
        # DatetimeIndex
        assert isinstance(result.index, pd.DatetimeIndex), (
            f"Expected DatetimeIndex, got {type(result.index)}"
        )
        # Columns are tickers
        assert sorted(result.columns.tolist()) == ["AAPL", "MSFT"]
        # Values are float dtype
        assert all(result.dtypes == float), f"Expected float dtypes, got {result.dtypes.to_dict()}"

    def test_signal_frame_contract(self) -> None:
        """SignalFrame index is tz-naive; values are float64 (not int)."""
        import pandas as pd
        import numpy as np

        rows = [
            ("AAPL", date(2024, 1, 2), 75),
            ("MSFT", date(2024, 1, 2), 60),
            ("AAPL", date(2024, 1, 3), 80),
        ]
        session = _make_session(rows)
        result = AiWashingLoader(session).load()

        # tz-naive: tzinfo must be None
        assert result.index.tzinfo is None, (
            f"Expected tz-naive DatetimeIndex, got tzinfo={result.index.tzinfo}"
        )
        # Float value check: 75 stored as 75.0
        aapl_first = result["AAPL"].iloc[0]
        assert aapl_first == 75.0, f"Expected 75.0, got {aapl_first}"
        assert isinstance(aapl_first, (float, np.floating)), (
            f"Expected float type, got {type(aapl_first)}"
        )


class TestAiWashingLoaderErrors:
    """AiWashingLoader.load() raises SignalLoadError on failure modes."""

    def test_load_raises_on_empty(self) -> None:
        """load() raises SignalLoadError when table returns no rows."""
        session = _make_session([])
        loader = AiWashingLoader(session)

        with pytest.raises(SignalLoadError) as exc_info:
            loader.load()

        assert "empty" in str(exc_info.value).lower(), (
            f"Expected 'empty' in error message, got: {exc_info.value}"
        )

    def test_load_raises_on_missing_table(self) -> None:
        """load() raises SignalLoadError when OperationalError occurs (DB/table unavailable)."""
        session = MagicMock()
        session.execute.side_effect = sqlalchemy.exc.OperationalError(
            "statement", {}, Exception("table daily_scores does not exist")
        )
        loader = AiWashingLoader(session)

        with pytest.raises(SignalLoadError) as exc_info:
            loader.load()

        assert "unavailable" in str(exc_info.value).lower(), (
            f"Expected 'unavailable' in error message, got: {exc_info.value}"
        )


class TestAiWashingLoaderDedup:
    """AiWashingLoader deduplicates multiple scores for same (ticker, date)."""

    def test_dedup_same_day_scores(self) -> None:
        """When two rows share ticker+date, last row wins (aggfunc='last')."""
        rows = [
            ("AAPL", date(2024, 1, 2), 60),
            ("AAPL", date(2024, 1, 2), 80),
        ]
        session = _make_session(rows)
        result = AiWashingLoader(session).load()

        # One row, one column
        assert result.shape == (1, 1), f"Expected (1, 1), got {result.shape}"
        # Last value wins
        assert result["AAPL"].iloc[0] == 80.0, (
            f"Expected last value 80.0, got {result['AAPL'].iloc[0]}"
        )
