"""Shared pytest fixtures for fund-backtest tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def sample_tickers() -> list[str]:
    """A small, stable set of tickers for unit tests."""
    return ["MTSI", "WTS", "GRBK", "SWX", "CALX"]


@pytest.fixture
def sample_wiki_row() -> dict:
    """A single row as returned by the Wikipedia S&P 400 scraper (post-rename)."""
    return {
        "ticker": "MTSI",
        "name": "MACOM Technology Solutions",
        "gics_sector": "Information Technology",
        "gics_sub_industry": "Semiconductors",
    }
