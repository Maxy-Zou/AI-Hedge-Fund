"""Unit tests for universe seeder and type contracts.

Tests cover:
- Wikipedia S&P 400 seeder column validation
- SeedRow Pydantic model (ticker strip, validation)
- UniverseEntry market cap filter (in-range, below, above, None)
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from fund_backtest.config import UniverseSettings
from fund_backtest.universe.seeder import fetch_sp400_seed
from fund_backtest.universe.types import SeedRow, UniverseEntry


def make_wiki_df() -> pd.DataFrame:
    """Return a minimal mock of the Wikipedia S&P 400 table."""
    return pd.DataFrame(
        {
            "Symbol": ["MTSI"],
            "Security": ["MACOM Technology Solutions"],
            "GICS Sector": ["Information Technology"],
            "GICS Sub-Industry": ["Semiconductors"],
        }
    )


# ---------------------------------------------------------------------------
# Seeder tests
# ---------------------------------------------------------------------------


def test_fetch_sp400_seed_column_validation_raises() -> None:
    """fetch_sp400_seed raises ValueError if expected columns are missing."""
    bad_df = pd.DataFrame({"col_a": [1], "col_b": [2]})
    with patch("fund_backtest.universe.seeder.pd.read_html", return_value=[bad_df]):
        with pytest.raises(ValueError, match="Symbol"):
            fetch_sp400_seed("https://example.com")


def test_fetch_sp400_seed_happy_path() -> None:
    """fetch_sp400_seed returns renamed columns from the Wikipedia table."""
    with patch("fund_backtest.universe.seeder.pd.read_html", return_value=[make_wiki_df()]):
        result = fetch_sp400_seed("https://example.com")

    assert list(result.columns) == ["ticker", "name", "gics_sector", "gics_sub_industry"]
    assert result.iloc[0]["ticker"] == "MTSI"
    assert result.iloc[0]["name"] == "MACOM Technology Solutions"
    assert result.iloc[0]["gics_sector"] == "Information Technology"
    assert result.iloc[0]["gics_sub_industry"] == "Semiconductors"
    # Exactly 4 columns — no extras
    assert len(result.columns) == 4


# ---------------------------------------------------------------------------
# SeedRow tests
# ---------------------------------------------------------------------------


def test_seedrow_valid() -> None:
    """SeedRow accepts valid data and stores ticker correctly."""
    row = SeedRow(
        ticker="MTSI",
        name="MACOM Technology Solutions",
        gics_sector="Information Technology",
        gics_sub_industry="Semiconductors",
    )
    assert row.ticker == "MTSI"


def test_seedrow_ticker_strip() -> None:
    """SeedRow strips whitespace from ticker field."""
    row = SeedRow(
        ticker=" MTSI ",
        name="MACOM Technology Solutions",
        gics_sector="Information Technology",
        gics_sub_industry="Semiconductors",
    )
    assert row.ticker == "MTSI"


# ---------------------------------------------------------------------------
# UniverseEntry market cap filter tests
# ---------------------------------------------------------------------------


def test_market_cap_filter_in_range() -> None:
    """UniverseEntry with $5B market cap passes mid-cap range check."""
    settings = UniverseSettings()
    entry = UniverseEntry(
        ticker="MTSI",
        name="MACOM Technology Solutions",
        market_cap_cents=500_000_000_000,  # $5B
    )
    assert entry.is_in_midcap_range(settings) is True


def test_market_cap_filter_below_range() -> None:
    """UniverseEntry with $1B market cap fails mid-cap range check."""
    settings = UniverseSettings()
    entry = UniverseEntry(
        ticker="MTSI",
        name="MACOM Technology Solutions",
        market_cap_cents=100_000_000_000,  # $1B
    )
    assert entry.is_in_midcap_range(settings) is False


def test_market_cap_filter_above_range() -> None:
    """UniverseEntry with $20B market cap fails mid-cap range check."""
    settings = UniverseSettings()
    entry = UniverseEntry(
        ticker="MSFT",
        name="Microsoft Corporation",
        market_cap_cents=2_000_000_000_000,  # $20B
    )
    assert entry.is_in_midcap_range(settings) is False


def test_market_cap_filter_none() -> None:
    """UniverseEntry with None market cap returns False (excluded)."""
    settings = UniverseSettings()
    entry = UniverseEntry(
        ticker="MTSI",
        name="MACOM Technology Solutions",
        market_cap_cents=None,
    )
    assert entry.is_in_midcap_range(settings) is False
