"""Wikipedia S&P 400 seed fetcher.

Fetches the S&P 400 constituent list from Wikipedia, validates column structure,
and returns a normalized DataFrame with standardized column names.

Usage:
    from fund_backtest.universe.seeder import fetch_sp400_seed
    df = fetch_sp400_seed("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies")
"""
from __future__ import annotations

import io
import urllib.request

import pandas as pd

EXPECTED_COLUMNS = {"Symbol", "Security", "GICS Sector", "GICS Sub-Industry"}

COLUMN_RENAME: dict[str, str] = {
    "Symbol": "ticker",
    "Security": "name",
    "GICS Sector": "gics_sector",
    "GICS Sub-Industry": "gics_sub_industry",
}

# Wikipedia blocks requests from the default pandas User-Agent (HTTP 403).
# Use a browser-like User-Agent to fetch the raw HTML, then parse in-memory.
_WIKIPEDIA_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def fetch_sp400_seed(url: str) -> pd.DataFrame:
    """Fetch S&P 400 constituents with GICS sector from Wikipedia.

    Validates that the returned table has the expected column structure before
    renaming. Raises ValueError immediately if columns are missing so callers
    get a clear signal that the Wikipedia page structure has changed.

    Uses a browser-like User-Agent header because Wikipedia blocks the default
    pandas User-Agent with HTTP 403 (as of 2026).

    Args:
        url: Wikipedia URL for the S&P 400 companies list.

    Returns:
        DataFrame with exactly 4 columns: ticker, name, gics_sector, gics_sub_industry.

    Raises:
        ValueError: If the fetched table lacks any of the expected columns.
        urllib.error.URLError: If the Wikipedia page is unreachable.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _WIKIPEDIA_USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        html_bytes = resp.read()

    tables = pd.read_html(io.BytesIO(html_bytes), flavor="lxml")
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
