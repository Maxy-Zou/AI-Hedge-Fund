"""ExampleStrategy — simple threshold-based buy strategy for Kalshi backtesting.

This module implements a minimal reference strategy that buys YES contracts when
the market's close price falls below a configurable threshold. It satisfies the
Strategy Protocol via structural subtyping — no inheritance required.

Usage:
    from kalshi_backtest.strategies.example import ExampleStrategy

    strategy = ExampleStrategy(buy_threshold=30, contracts=1)
    signals = strategy.generate_signals(snapshot, open_positions)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from kalshi_backtest.simulation.protocol import Signal

if TYPE_CHECKING:
    from kalshi_backtest.simulation.protocol import Position
    from kalshi_backtest.simulation.snapshot import MarketSnapshot

logger = structlog.get_logger(__name__)


class ExampleStrategy:
    """Buy YES when the close price is strictly below a threshold.

    A minimal reference implementation of the Strategy Protocol. Useful for
    verifying the backtesting pipeline end-to-end without a real signal source.

    Attributes:
        _threshold: Maximum price (exclusive) at which to buy, in cents [0, 100].
        _contracts: Number of contracts per signal.

    Args:
        buy_threshold: Buy when close_price < buy_threshold (cents). Default 40.
        contracts: Number of contracts per signal. Default 1.
    """

    def __init__(self, buy_threshold: int = 40, contracts: int = 1) -> None:
        """Initialise ExampleStrategy.

        Args:
            buy_threshold: Price ceiling (exclusive) for generating a buy signal.
            contracts: Number of contracts to request per signal.
        """
        self._threshold = buy_threshold
        self._contracts = contracts
        self._log = logger.bind(strategy="ExampleStrategy")

    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]:
        """Return a buy signal if the close price is below the threshold.

        Args:
            snapshot: Look-ahead-safe view of a market bar. Uses .ticker,
                .close_price (int cents), and .ts (naive UTC datetime).
            open_positions: Currently held positions. Each has a .ticker attribute.
                If the snapshot ticker is already held, no new signal is generated
                to avoid pyramiding.

        Returns:
            A list containing one Signal if conditions are met, otherwise [].
        """
        held = {p.ticker for p in open_positions}

        if snapshot.ticker in held:
            self._log.debug(
                "example_strategy_skip_held",
                ticker=snapshot.ticker,
            )
            return []

        if snapshot.close_price < self._threshold:
            signal = Signal(
                ticker=snapshot.ticker,
                direction="yes",
                contracts=self._contracts,
                limit_price=snapshot.close_price,
                reason=f"example:price_below_{self._threshold}",
            )
            self._log.info(
                "example_strategy_signal",
                ticker=snapshot.ticker,
                close_price=snapshot.close_price,
                threshold=self._threshold,
            )
            return [signal]

        return []
