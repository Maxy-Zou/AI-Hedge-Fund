"""Quick ingestion: fetch political/economic markets with candlestick data.

Uses the live API series→markets→candlesticks path, which returns proper
OHLC data. Targets series with political/economic keywords.

Usage:
    PYTHONUNBUFFERED=1 python scripts/quick_ingest.py
"""
from __future__ import annotations

import math
import sys
import time
from datetime import UTC, datetime, timedelta

import httpx
from kalshi_python.api_client import KalshiAuth

from kalshi_backtest.config import load_settings
from kalshi_backtest.db.repository import MarketRepository
from kalshi_backtest.db.schema import get_or_create_db
from kalshi_backtest.ingestion.types import CandlestickRecord, MarketRecord

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

KEYWORDS = [
    "fed", "rate", "tariff", "trump", "president", "congress", "senate",
    "election", "vote", "approval", "gdp", "inflation", "unemployment",
    "recession", "government", "executive", "cabinet", "impeach", "policy",
    "scotus", "court", "debt", "budget", "cpi", "jobs", "oil", "gas",
    "bitcoin", "crypto", "sp500", "nasdaq", "dow", "stock", "housing",
]

TARGET_MARKETS = 300


def _parse_live_candle(ticker: str, c: dict) -> CandlestickRecord | None:
    """Parse a candlestick from the live API format.

    Live API returns prices in dollar strings inside nested dicts:
        {"yes_ask": {"close_dollars": "0.55", ...}, "yes_bid": {...}}

    We convert to integer cents and use the midpoint of bid/ask close as close_price.
    """
    ts = c.get("end_period_ts")
    if ts is None:
        return None

    def _dollars_to_cents(d: str | None) -> int | None:
        if d is None:
            return None
        try:
            return int(round(float(d) * 100))
        except (ValueError, TypeError):
            return None

    yes_ask = c.get("yes_ask", {})
    yes_bid = c.get("yes_bid", {})

    ask_close = _dollars_to_cents(yes_ask.get("close_dollars"))
    bid_close = _dollars_to_cents(yes_bid.get("close_dollars"))
    ask_high = _dollars_to_cents(yes_ask.get("high_dollars"))
    bid_low = _dollars_to_cents(yes_bid.get("low_dollars"))
    ask_open = _dollars_to_cents(yes_ask.get("open_dollars"))

    # Use midpoint of bid/ask as price, fallback to ask
    if ask_close is not None and bid_close is not None:
        close_price = (ask_close + bid_close) // 2
    elif ask_close is not None:
        close_price = ask_close
    elif bid_close is not None:
        close_price = bid_close
    else:
        return None

    # Clamp to [0, 100]
    close_price = max(0, min(100, close_price))

    open_price = ask_open
    if open_price is not None:
        open_price = max(0, min(100, open_price))

    high_price = ask_high
    if high_price is not None:
        high_price = max(0, min(100, high_price))

    low_price = bid_low
    if low_price is not None:
        low_price = max(0, min(100, low_price))

    volume_str = c.get("volume_fp")
    volume = int(float(volume_str)) if volume_str else None

    try:
        return CandlestickRecord(
            ticker=ticker,
            ts=ts,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=volume,
        )
    except Exception:
        return None


def main() -> None:
    settings = load_settings()
    auth = KalshiAuth(
        key_id=settings.api_key_id,
        private_key_path=str(settings.private_key_path),
    )
    http = httpx.Client(timeout=30.0)
    con = get_or_create_db(settings.db_path)
    repo = MarketRepository(con)

    # Step 1: Get all series and filter for political/economic ones
    print("Step 1: Finding political/economic series...")
    url = f"{API_BASE}/series"
    headers = auth.create_auth_headers("GET", url)
    resp = http.get(url, params={"limit": 200}, headers=headers)
    all_series = resp.json().get("series", [])

    matching_series = []
    for s in all_series:
        text = (s.get("title", "") + " " + s.get("ticker", "")).lower()
        if any(kw in text for kw in KEYWORDS):
            matching_series.append(s["ticker"])

    print(f"  Found {len(matching_series)} matching series out of {len(all_series)}")

    # Step 2: For each series, get settled markets
    print("\nStep 2: Fetching settled markets from matching series...")
    all_markets: list[tuple[MarketRecord, str]] = []  # (record, series_ticker)

    for i, series_ticker in enumerate(matching_series):
        if len(all_markets) >= TARGET_MARKETS:
            break

        url = f"{API_BASE}/markets"
        headers = auth.create_auth_headers("GET", url)
        resp = http.get(url, params={
            "series_ticker": series_ticker,
            "limit": 50,
            "status": "settled",
        }, headers=headers)

        if resp.status_code != 200:
            continue

        for m in resp.json().get("markets", []):
            result = m.get("result")
            if not result:
                continue
            try:
                record = MarketRecord(
                    ticker=m["ticker"],
                    event_ticker=m.get("event_ticker", ""),
                    series_ticker=series_ticker,
                    subtitle=m.get("subtitle") or m.get("yes_sub_title"),
                    open_time=m.get("open_time", ""),
                    close_time=m.get("close_time", ""),
                    expiration_time=m.get("expiration_time"),
                    status=m.get("status", "unknown"),
                    result=result,
                )
                all_markets.append((record, series_ticker))
            except Exception:
                continue

        if (i + 1) % 20 == 0:
            print(f"  [{i + 1}/{len(matching_series)}] Markets: {len(all_markets)}")

        time.sleep(0.3)

    print(f"  Collected {len(all_markets)} settled markets")

    # Step 3: Upsert markets
    print("\nStep 3: Upserting markets...")
    for market, _ in all_markets:
        safe_result = market.result if market.status in ("settled", "finalized") else None
        safe_market = market.model_copy(update={"result": safe_result})
        repo.upsert_market(safe_market)
    print(f"  Upserted {len(all_markets)} markets")

    # Step 4: Fetch candlesticks via live endpoint
    print("\nStep 4: Fetching candlesticks...")
    candle_count = 0
    failures = 0
    markets_with_candles = 0

    for i, (market, series_ticker) in enumerate(all_markets):
        try:
            start_ts = int(market.open_time.timestamp())
            end_ts = int(market.close_time.timestamp()) + 86400

            url = f"{API_BASE}/series/{series_ticker}/markets/{market.ticker}/candlesticks"
            headers = auth.create_auth_headers("GET", url)
            resp = http.get(url, params={
                "start_ts": start_ts,
                "end_ts": end_ts,
                "period_interval": 1440,
            }, headers=headers)

            if resp.status_code != 200:
                failures += 1
                continue

            raw_candles = resp.json().get("candlesticks", [])
            candles = []
            for c in raw_candles:
                record = _parse_live_candle(market.ticker, c)
                if record is not None:
                    candles.append(record)

            if candles:
                repo.insert_candles(candles)
                candle_count += len(candles)
                markets_with_candles += 1

            if (i + 1) % 25 == 0:
                print(
                    f"  [{i + 1}/{len(all_markets)}] "
                    f"Candles: {candle_count}, "
                    f"Markets w/ data: {markets_with_candles}, "
                    f"Failures: {failures}"
                )

            time.sleep(0.3)

        except Exception:
            failures += 1
            continue

    print(
        f"\nDone! Markets: {len(all_markets)}, "
        f"Markets with candles: {markets_with_candles}, "
        f"Total candles: {candle_count}, "
        f"Failures: {failures}"
    )
    con.close()
    http.close()


if __name__ == "__main__":
    main()
