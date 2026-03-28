"""Wikipedia S&P 400 seed fetcher.

Fetches the S&P 400 constituent list from Wikipedia, validates column structure,
and returns a normalized DataFrame with standardized column names.

Usage:
    from fund_backtest.universe.seeder import fetch_sp400_seed
    df = fetch_sp400_seed("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies")
"""
from __future__ import annotations

import pandas as pd

EXPECTED_COLUMNS = {"Symbol", "Security", "GICS Sector", "GICS Sub-Industry"}

COLUMN_RENAME: dict[str, str] = {
    "Symbol": "ticker",
    "Security": "name",
    "GICS Sector": "gics_sector",
    "GICS Sub-Industry": "gics_sub_industry",
}


def fetch_sp400_seed(url: str) -> pd.DataFrame:
    """Fetch S&P 400 constituents with GICS sector from Wikipedia.

    Validates that the returned table has the expected column structure before
    renaming. Raises ValueError immediately if columns are missing so callers
    get a clear signal that the Wikipedia page structure has changed.

    Args:
        url: Wikipedia URL for the S&P 400 companies list.

    Returns:
        DataFrame with exactly 4 columns: ticker, name, gics_sector, gics_sub_industry.

    Raises:
        ValueError: If the fetched table lacks any of the expected columns.
    """
    tables = pd.read_html(url, flavor="lxml")
    df = tables[0]

    missing = EXPECTED_COLUMNS - set(df.columns)
    if missing:
        msg = (
            f"Wikipedia S&P 400 table missing expected columns: {sorted(missing)}. "
            f"Found: {sorted(df.columns.tolist())}. "
            "The Wikipedia page structure may have changed."
        )
        raise ValueError(msg)

    return df.rename(columns=COLUMN_RENAME)[list(COLUMN_RENAME.values())]
