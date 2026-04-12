"""Temporal enforcement utilities for data ingestion.

Every data tool function must use the @enforce_as_of_date decorator to
prevent look-ahead bias. The decorator validates that as_of_date is
provided, is not in the future, and normalizes datetime to date.
"""

from __future__ import annotations

import functools
import inspect
from datetime import date, datetime
from typing import Any


def normalize_as_of_date(as_of_date: date | datetime | None) -> date:
    """Validate and normalize an as_of_date parameter.

    Args:
        as_of_date: The date to validate. Must not be None or in the future.
            datetime values are converted to date.

    Returns:
        Validated date instance.

    Raises:
        ValueError: If as_of_date is None or in the future.
    """
    if as_of_date is None:
        msg = "as_of_date is required -- every data retrieval must specify a temporal cutoff"
        raise ValueError(msg)

    # Convert datetime to date (check datetime before date since datetime is subclass of date)
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.date()

    if as_of_date > date.today():
        msg = f"as_of_date ({as_of_date}) cannot be in the future"
        raise ValueError(msg)

    return as_of_date


def enforce_as_of_date(func: Any) -> Any:
    """Decorator that enforces as_of_date validation on data tool functions.

    Intercepts the `as_of_date` keyword argument, validates it via
    normalize_as_of_date, and passes the normalized date to the wrapped
    function. Works with both sync and async functions.

    Args:
        func: Function with an `as_of_date` keyword parameter.

    Returns:
        Wrapped function with as_of_date enforcement.
    """
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            raw_date = kwargs.get("as_of_date")
            kwargs["as_of_date"] = normalize_as_of_date(raw_date)
            return await func(*args, **kwargs)

        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        raw_date = kwargs.get("as_of_date")
        kwargs["as_of_date"] = normalize_as_of_date(raw_date)
        return func(*args, **kwargs)

    return sync_wrapper
