"""Tests for temporal enforcement utilities.

Validates that the as_of_date enforcement decorator and normalizer
reject None values, future dates, and correctly convert datetime to date.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from ai_hedge_fund.data.temporal import enforce_as_of_date, normalize_as_of_date


class TestNormalizeAsOfDate:
    """Tests for normalize_as_of_date utility."""

    def test_none_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="as_of_date is required"):
            normalize_as_of_date(None)

    def test_future_date_raises_value_error(self) -> None:
        future = date.today() + timedelta(days=1)
        with pytest.raises(ValueError, match="cannot be in the future"):
            normalize_as_of_date(future)

    def test_datetime_converted_to_date(self) -> None:
        dt = datetime(2024, 6, 15, 14, 30, 0, tzinfo=UTC)
        result = normalize_as_of_date(dt)
        assert result == date(2024, 6, 15)
        assert isinstance(result, date)
        assert not isinstance(result, datetime)

    def test_valid_date_passes_through(self) -> None:
        d = date(2024, 6, 15)
        result = normalize_as_of_date(d)
        assert result == d

    def test_today_is_valid(self) -> None:
        result = normalize_as_of_date(date.today())
        assert result == date.today()

    def test_naive_datetime_converted_to_date(self) -> None:
        dt = datetime(2024, 3, 10, 9, 0, 0)
        result = normalize_as_of_date(dt)
        assert result == date(2024, 3, 10)


class TestEnforceAsOfDate:
    """Tests for enforce_as_of_date decorator."""

    def test_missing_as_of_date_raises_value_error(self) -> None:
        @enforce_as_of_date
        def fetch_data(*, as_of_date: date | None = None) -> str:
            return "data"

        with pytest.raises(ValueError, match="as_of_date is required"):
            fetch_data()

    def test_none_as_of_date_raises_value_error(self) -> None:
        @enforce_as_of_date
        def fetch_data(*, as_of_date: date | None = None) -> str:
            return "data"

        with pytest.raises(ValueError, match="as_of_date is required"):
            fetch_data(as_of_date=None)

    def test_future_as_of_date_raises_value_error(self) -> None:
        @enforce_as_of_date
        def fetch_data(*, as_of_date: date | None = None) -> str:
            return "data"

        future = date.today() + timedelta(days=1)
        with pytest.raises(ValueError, match="cannot be in the future"):
            fetch_data(as_of_date=future)

    def test_datetime_converted_to_date(self) -> None:
        @enforce_as_of_date
        def fetch_data(*, as_of_date: date | None = None) -> date:
            return as_of_date  # type: ignore[return-value]

        dt = datetime(2024, 6, 15, 14, 30, 0, tzinfo=UTC)
        result = fetch_data(as_of_date=dt)
        assert result == date(2024, 6, 15)
        assert isinstance(result, date)
        assert not isinstance(result, datetime)

    def test_valid_date_passes_through(self) -> None:
        @enforce_as_of_date
        def fetch_data(*, as_of_date: date | None = None) -> date:
            return as_of_date  # type: ignore[return-value]

        d = date(2024, 6, 15)
        result = fetch_data(as_of_date=d)
        assert result == d

    def test_preserves_other_arguments(self) -> None:
        @enforce_as_of_date
        def fetch_data(
            ticker: str, *, as_of_date: date | None = None, limit: int = 10
        ) -> tuple[str, date, int]:
            return (ticker, as_of_date, limit)  # type: ignore[return-value]

        d = date(2024, 6, 15)
        result = fetch_data("AAPL", as_of_date=d, limit=5)
        assert result == ("AAPL", d, 5)

    def test_preserves_function_name(self) -> None:
        @enforce_as_of_date
        def fetch_data(*, as_of_date: date | None = None) -> str:
            return "data"

        assert fetch_data.__name__ == "fetch_data"
