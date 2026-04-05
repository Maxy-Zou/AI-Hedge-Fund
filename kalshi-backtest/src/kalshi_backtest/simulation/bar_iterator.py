"""BarIterator — bulk-load + event-driven chronological replay with look-ahead prevention.

Design: All market and candle data is loaded at construction time (bulk load). During
iteration, bars are sorted by timestamp and yielded in strict chronological order across
all tickers. This hybrid approach prevents look-ahead by:
1. The result firewall: suppress_result=True is passed to build_snapshot() whenever
   candle.ts < market.close_time, physically preventing the strategy from seeing the
   settlement outcome before it happens.
2. No database calls during __iter__: data is frozen at construction — no mid-replay
   queries that could accidentally expose future information.

Usage:
    markets = repository.get_markets(series_ticker="KXBTC")
    candles_by_ticker = {m["ticker"]: repository.get_candles(m["ticker"]) for m in markets}
    for snapshot in BarIterator(markets, candles_by_ticker):
        signals = strategy.generate_signals(snapshot, open_positions)
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterator

import structlog

from kalshi_backtest.simulation.snapshot import MarketSnapshot, build_snapshot

logger = structlog.get_logger(__name__).bind(component="BarIterator")


class BarIterator:
    """Replay all candles across all tickers in strict chronological order.

    Enforces the look-ahead firewall: any bar with ts < market.close_time will have
    result=None in the yielded snapshot, making it impossible for a strategy to
    trade on settlement knowledge before it occurs.

    Args:
        markets: List of market dicts (from repository.get_markets()).
        candles_by_ticker: Mapping of ticker -> list of candle dicts
                           (from repository.get_candles()).
    """

    def __init__(
        self,
        markets: list[dict],
        candles_by_ticker: dict[str, list[dict]],
    ) -> None:
        """Store market data and build O(1) ticker->market lookup map."""
        self._markets = markets
        self._candles_by_ticker = candles_by_ticker
        # O(1) lookup: ticker -> market dict
        self._market_map: dict[str, dict] = {m["ticker"]: m for m in markets}

    def __iter__(self) -> Iterator[MarketSnapshot]:
        """Yield MarketSnapshot for every candle in strict chronological order.

        Collects all (ts, ticker, candle) tuples from all tickers, sorts by ts ascending,
        then yields build_snapshot() for each. The suppress_result flag implements the
        look-ahead firewall: set to True whenever candle.ts < market.close_time.

        Yields:
            MarketSnapshot with result=None for pre-settlement bars, result exposed
            at and after close_time when market.result is known.
        """
        # Collect all bars as (ts, ticker, candle) tuples for global sort
        all_bars: list[tuple[datetime, str, dict]] = []
        for ticker, candles in self._candles_by_ticker.items():
            if ticker not in self._market_map:
                logger.warning("candles_for_unknown_ticker", ticker=ticker)
                continue
            for candle in candles:
                ts = candle["ts"]
                all_bars.append((ts, ticker, candle))

        # Sort by ts ascending — strict chronological order across all tickers
        all_bars.sort(key=lambda x: x[0])

        for ts, ticker, candle in all_bars:
            market = self._market_map[ticker]
            close_time = market["close_time"]

            # Look-ahead firewall: suppress result for any bar before settlement
            suppress_result = ts < close_time

            yield build_snapshot(market, candle, suppress_result=suppress_result)

    def bar_count(self) -> int:
        """Return total number of bars across all tickers.

        Used for progress reporting in the BacktestRunner.

        Returns:
            Total candle count across all tickers in candles_by_ticker.
        """
        return sum(len(candles) for candles in self._candles_by_ticker.values())
