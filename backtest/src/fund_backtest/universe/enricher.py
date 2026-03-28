"""yfinance market cap and sector enricher with rate limiting and retry.

Fetches market cap and sector data for each ticker in the universe,
applying Wikipedia sector precedence over yfinance sector data.

Usage:
    from fund_backtest.universe.enricher import fetch_ticker_info, enrich_universe
"""
from __future__ import annotations

import time

import structlog
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from fund_backtest.universe.types import SeedRow, UniverseEntry

log = structlog.get_logger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def fetch_ticker_info(ticker: str) -> dict:
    """Fetch market cap and sector for a single ticker from yfinance.

    Applies tenacity retry with exponential backoff to handle transient
    yfinance failures. market_cap_cents is always an int (never a float).

    Args:
        ticker: Exchange symbol to look up.

    Returns:
        dict with keys:
            market_cap_cents (int | None): Market cap in cents. None if unavailable.
            yfinance_sector (str | None): Sector string from yfinance. None if unavailable.

    Note:
        market_cap_cents = int(marketCap * 100). Never stores floats for market cap.
    """
    info = yf.Ticker(ticker).info
    raw_cap = info.get("marketCap")
    market_cap_cents = int(raw_cap * 100) if raw_cap is not None else None
    return {
        "market_cap_cents": market_cap_cents,
        "yfinance_sector": info.get("sector"),
    }


def build_universe_entry(seed_row: SeedRow, yf_data: dict) -> UniverseEntry:
    """Build a UniverseEntry by merging seed data with yfinance enrichment.

    Sector precedence: Wikipedia S&P 400 > yfinance > None.
    Wikipedia sector is more authoritative (official GICS classification from S&P).

    Args:
        seed_row: Row from the Wikipedia S&P 400 seed.
        yf_data: Dict from fetch_ticker_info with market_cap_cents and yfinance_sector.

    Returns:
        UniverseEntry with merged data and sector_source set appropriately.
    """
    if seed_row.gics_sector is not None:
        gics_sector = seed_row.gics_sector
        sector_source: str | None = "wikipedia_sp400"
    elif yf_data.get("yfinance_sector") is not None:
        gics_sector = yf_data["yfinance_sector"]
        sector_source = "yfinance"
    else:
        gics_sector = None
        sector_source = None
        log.warning("no_sector_found", ticker=seed_row.ticker)

    return UniverseEntry(
        ticker=seed_row.ticker,
        name=seed_row.name,
        gics_sector=gics_sector,
        gics_sub_industry=seed_row.gics_sub_industry,
        market_cap_cents=yf_data.get("market_cap_cents"),
        sector_source=sector_source,
    )


def enrich_universe(
    seed_rows: list[SeedRow],
    delay_secs: float = 1.0,
) -> list[UniverseEntry]:
    """Fetch market cap and sector for all seed rows.

    Rate-limited to ~1 req/sec (configurable) to respect Yahoo Finance limits.
    Logs a warning for any ticker where yfinance returns no data but continues
    processing remaining tickers (graceful degradation).

    Args:
        seed_rows: List of seed rows from Wikipedia S&P 400 scraper.
        delay_secs: Delay between yfinance requests in seconds. Default 1.0.

    Returns:
        List of UniverseEntry objects with enriched market cap and sector data.
    """
    entries: list[UniverseEntry] = []
    for row in seed_rows:
        try:
            yf_data = fetch_ticker_info(row.ticker)
        except Exception:
            log.warning("yfinance_fetch_failed", ticker=row.ticker)
            yf_data = {"market_cap_cents": None, "yfinance_sector": None}
        entry = build_universe_entry(row, yf_data)
        entries.append(entry)
        time.sleep(delay_secs)
    return entries
