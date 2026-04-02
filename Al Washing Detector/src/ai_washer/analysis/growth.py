"""Growth rate computation utilities.

Provides CAGR calculation and yearly series building from XBRL facts.
Used by both SEC filing scorer and compute spending scorer to measure
growth trends in keyword frequency and financial spending.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence


def compute_cagr(
    start_value: float,
    end_value: float,
    years: int,
) -> float | None:
    """Compute Compound Annual Growth Rate.

    Args:
        start_value: Beginning period value.
        end_value: Ending period value.
        years: Number of years between start and end.

    Returns:
        CAGR as a float (e.g., 0.25 for 25% growth), or None if
        start_value <= 0 or years <= 0 (cannot compute growth).
        Returns -1.0 if end_value <= 0 (total decline).
    """
    if start_value <= 0 or years <= 0:
        return None
    if end_value <= 0:
        return -1.0
    return (end_value / start_value) ** (1.0 / years) - 1.0


def build_yearly_series(
    facts: Sequence[tuple[int, str, int]],
) -> dict[int, int]:
    """Build fiscal_year -> value_cents mapping from XBRL fact tuples.

    Args:
        facts: Sequence of (fiscal_year, fiscal_period, value_cents) tuples.
               fiscal_period is like "FY", "Q1", "Q2", "Q3", "Q4".
               Prefers "FY" over quarterly values for the same year.

    Returns:
        Sorted dict mapping fiscal_year to value_cents.
        When multiple entries exist for the same year:
        - If "FY" exists, use it
        - If all four Q1-Q4 exist, sum them
        - Otherwise take the single largest quarterly value
    """
    if not facts:
        return {}

    # Group by fiscal year
    by_year: dict[int, dict[str, int]] = defaultdict(dict)
    for fiscal_year, fiscal_period, value_cents in facts:
        by_year[fiscal_year][fiscal_period] = value_cents

    result: dict[int, int] = {}
    for year, periods in by_year.items():
        if "FY" in periods:
            result[year] = periods["FY"]
        elif all(q in periods for q in ("Q1", "Q2", "Q3", "Q4")):
            result[year] = (
                periods["Q1"] + periods["Q2"] + periods["Q3"] + periods["Q4"]
            )
        else:
            # Take the maximum quarterly value
            quarterly_values = [
                v for k, v in periods.items() if k.startswith("Q")
            ]
            if quarterly_values:
                result[year] = max(quarterly_values)

    return dict(sorted(result.items()))
