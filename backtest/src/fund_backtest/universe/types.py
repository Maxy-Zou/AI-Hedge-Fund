"""Pydantic type contracts for the universe module.

Provides:
- SeedRow: A single row from the Wikipedia S&P 400 seed table
- UniverseEntry: A ticker with enriched data, ready for DB upsert
- RefreshResult: Summary of a universe refresh run
"""
from __future__ import annotations

import math

from pydantic import BaseModel, Field, field_validator

from fund_backtest.config import UniverseSettings


def _nan_to_none(v: object) -> object:
    """Convert float NaN (pandas missing value) to None.

    pandas uses float('nan') for missing string cells; Pydantic v2 does not
    coerce NaN to None automatically for str | None fields.
    """
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


class SeedRow(BaseModel):
    """A single row from the Wikipedia S&P 400 seed table.

    Represents a company as returned by the Wikipedia scraper,
    before yfinance enrichment. ticker is stripped of whitespace.
    """

    ticker: str
    name: str
    gics_sector: str | None = None
    gics_sub_industry: str | None = None

    @field_validator("ticker", mode="before")
    @classmethod
    def strip_ticker(cls, v: str) -> str:
        """Strip leading/trailing whitespace from ticker symbol."""
        return v.strip()

    @field_validator("gics_sector", "gics_sub_industry", mode="before")
    @classmethod
    def coerce_nan_to_none(cls, v: object) -> object:
        """Convert pandas float NaN to None for optional string fields."""
        return _nan_to_none(v)


class UniverseEntry(BaseModel):
    """A ticker with all enriched data, ready for DB upsert.

    Combines Wikipedia seed data with yfinance enrichment.
    market_cap_cents is always stored as an integer (cents), never a float.
    """

    ticker: str
    name: str
    gics_sector: str | None = None
    gics_sub_industry: str | None = None
    market_cap_cents: int | None = None  # cents (dollars * 100), never float
    sector_source: str | None = None  # "wikipedia_sp400" | "yfinance" | "manual"

    def is_in_midcap_range(self, settings: UniverseSettings) -> bool:
        """Return True if market cap is within the configured mid-cap bounds.

        Args:
            settings: Universe configuration with market cap bounds in cents.

        Returns:
            True if market_cap_cents is within [min, max] inclusive.
            False if market_cap_cents is None (unknown cap excluded).
        """
        if self.market_cap_cents is None:
            return False
        return settings.market_cap_min_cents <= self.market_cap_cents <= settings.market_cap_max_cents


class RefreshResult(BaseModel):
    """Summary of a universe refresh run.

    Returned by UniverseBuilder.refresh() to describe what changed.
    """

    snapshot_date: str  # ISO date string e.g. "2026-03-28"
    active_count: int
    new_count: int
    removed_count: int
    sector_breakdown: dict[str, int] = Field(default_factory=dict)
