"""BacktestRunner — orchestrates the full bar-by-bar simulation loop.

Role: The top-level coordinator for a single backtest run. Wires together all
prior simulation components in the correct order:

    MarketRepository → bulk-load → BarIterator
    BarIterator → yield snapshot → Strategy.generate_signals()
    Signal → FillEngine.try_fill() → Fill → PositionTracker.open()
    snapshot.result not None → PositionTracker.settle()
    End of loop → BacktestResult

The BarIterator is the look-ahead guardian — no snapshot passed to
generate_signals() will ever expose the settlement result before close_time.

BacktestResult is the primary data contract consumed by Phase 3 (metrics layer).
Its shape is finalized here and must not change without a migration plan.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
import structlog

from kalshi_backtest.db.repository import MarketRepository
from kalshi_backtest.simulation.bar_iterator import BarIterator
from kalshi_backtest.simulation.fill_engine import FillEngine
from kalshi_backtest.simulation.position_tracker import PositionTracker
from kalshi_backtest.simulation.protocol import Strategy

logger = structlog.get_logger(__name__).bind(component="BacktestRunner")


# ---------------------------------------------------------------------------
# BacktestResult — immutable output contract for Phase 3
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestResult:
    """Immutable result of a completed backtest run.

    This is the primary data contract consumed by the metrics layer (Phase 3).
    All fields are set once at the end of BacktestRunner.run() and never mutated.

    Attributes:
        run_id: UUID4 string uniquely identifying this run.
        strategy_name: Class name of the Strategy used.
        start_date: Inclusive start of the backtest window (naive UTC).
        end_date: Inclusive end of the backtest window (naive UTC).
        trade_log: Full trade history as a DataFrame. One row per closed position.
            Columns: ticker, direction, contracts, entry_price, entry_ts,
                     exit_price, exit_ts, pnl_cents, fee_cents, exit_reason.
        daily_pnl: Daily P&L aggregated by exit date (pd.Series, date index).
        total_pnl_cents: Sum of all pnl_cents across the run (integer cents).
        total_fees_cents: Sum of all fee_cents across the run (integer cents).
        settled_contracts: Total contracts that reached settlement (not mark-to-market).
        open_contracts: Contracts still open at end_date (unrealized exposure).
    """

    run_id: str
    strategy_name: str
    start_date: datetime
    end_date: datetime
    trade_log: pd.DataFrame
    daily_pnl: pd.Series
    total_pnl_cents: int
    total_fees_cents: int
    settled_contracts: int
    open_contracts: int

    def __eq__(self, other: object) -> bool:
        """Custom equality — DataFrames/Series require special handling."""
        if not isinstance(other, BacktestResult):
            return NotImplemented
        return (
            self.run_id == other.run_id
            and self.strategy_name == other.strategy_name
            and self.start_date == other.start_date
            and self.end_date == other.end_date
            and self.total_pnl_cents == other.total_pnl_cents
            and self.total_fees_cents == other.total_fees_cents
            and self.settled_contracts == other.settled_contracts
            and self.open_contracts == other.open_contracts
        )


# ---------------------------------------------------------------------------
# BacktestRunner — orchestration engine
# ---------------------------------------------------------------------------


class BacktestRunner:
    """Drives a complete bar-by-bar simulation against historical Kalshi data.

    Wires together BarIterator (look-ahead safety), Strategy (signal generation),
    FillEngine (fill execution), and PositionTracker (position lifecycle).

    Args:
        repo: MarketRepository providing access to the DuckDB store.
        fill_engine: Optional FillEngine instance. Defaults to FillEngine(spread_floor=1).
    """

    def __init__(
        self,
        repo: MarketRepository,
        fill_engine: FillEngine | None = None,
    ) -> None:
        self._repo = repo
        self._fill_engine = fill_engine or FillEngine(spread_floor=1)

    def run(
        self,
        strategy: Strategy,
        start_date: datetime,
        end_date: datetime,
        series_tickers: list[str] | None = None,
    ) -> BacktestResult:
        """Execute a full backtest over the given date window.

        Steps:
        1. Load markets from the repo filtered by date range (and series).
        2. Bulk-load candles for each market ticker.
        3. Construct BarIterator for look-ahead-safe chronological replay.
        4. Bar-by-bar loop: generate signals → try fills → settle on result.
        5. Build and return BacktestResult from PositionTracker state.

        Args:
            strategy: Any Strategy-protocol object with generate_signals().
            start_date: Lower bound for market close_time filter (naive UTC).
            end_date: Upper bound for market close_time filter (naive UTC).
            series_tickers: Optional whitelist of series_ticker values to include.
                            None means all series.

        Returns:
            BacktestResult with complete trade log, daily P&L, and summary metrics.
        """
        run_id = str(uuid.uuid4())
        strategy_name = type(strategy).__name__
        log = logger.bind(run_id=run_id, strategy=strategy_name)
        log.info("backtest_run_started", start_date=start_date, end_date=end_date)

        # --- 1. Load markets ---
        if series_tickers is not None:
            markets: list[dict] = []
            for st in series_tickers:
                markets.extend(
                    self._repo.get_markets(
                        series_ticker=st,
                        min_close_time=start_date,
                        max_close_time=end_date,
                    )
                )
        else:
            markets = self._repo.get_markets(
                min_close_time=start_date,
                max_close_time=end_date,
            )

        if not markets:
            log.info("backtest_run_no_markets")
            return self._build_empty_result(run_id, strategy_name, start_date, end_date)

        # --- 2. Bulk-load candles ---
        candles_by_ticker: dict[str, list[dict]] = {}
        for market in markets:
            ticker = market["ticker"]
            candles_by_ticker[ticker] = self._repo.get_candles(
                ticker,
                start_ts=start_date,
            )

        # --- 3. Construct BarIterator ---
        bar_iterator = BarIterator(markets, candles_by_ticker)
        log.info(
            "backtest_data_loaded",
            market_count=len(markets),
            bar_count=bar_iterator.bar_count(),
        )

        # --- 4. Main bar-by-bar loop ---
        tracker = PositionTracker()
        settled_tickers: set[str] = set()  # prevent double-settlement
        fill_count = 0

        for snapshot in bar_iterator:
            # a) Generate signals from strategy
            signals = strategy.generate_signals(snapshot, tracker.open_positions)

            # b) Try to fill each signal
            for signal in signals:
                fill = self._fill_engine.try_fill(signal, snapshot)
                if fill is not None:
                    tracker.open(fill)
                    fill_count += 1

            # c) Settle if market has resolved and not yet settled
            if snapshot.result is not None and snapshot.ticker not in settled_tickers:
                tracker.settle(
                    ticker=snapshot.ticker,
                    result=snapshot.result,
                    ts=snapshot.ts,
                )
                settled_tickers.add(snapshot.ticker)

        # --- 5. Build BacktestResult ---
        trade_log = tracker.to_trade_log()
        daily_pnl = tracker.to_daily_pnl_series()

        total_pnl = int(trade_log["pnl_cents"].sum()) if len(trade_log) > 0 else 0
        total_fees = int(trade_log["fee_cents"].sum()) if len(trade_log) > 0 else 0

        # Settled contracts: sum contracts where exit_reason == 'settlement'
        if len(trade_log) > 0:
            settled_mask = trade_log["exit_reason"] == "settlement"
            settled_contracts = int(trade_log.loc[settled_mask, "contracts"].sum())
        else:
            settled_contracts = 0

        open_contracts = sum(p.contracts for p in tracker.open_positions)

        log.info(
            "backtest_run_complete",
            bar_count=bar_iterator.bar_count(),
            fill_count=fill_count,
            settled_contracts=settled_contracts,
            open_contracts=open_contracts,
            total_pnl_cents=total_pnl,
        )

        return BacktestResult(
            run_id=run_id,
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            trade_log=trade_log,
            daily_pnl=daily_pnl,
            total_pnl_cents=total_pnl,
            total_fees_cents=total_fees,
            settled_contracts=settled_contracts,
            open_contracts=open_contracts,
        )

    def _build_empty_result(
        self,
        run_id: str,
        strategy_name: str,
        start_date: datetime,
        end_date: datetime,
    ) -> BacktestResult:
        """Build a BacktestResult with no trades when no markets are found.

        Args:
            run_id: The run UUID.
            strategy_name: The strategy class name.
            start_date: Run start date.
            end_date: Run end date.

        Returns:
            BacktestResult with empty trade_log and zero metrics.
        """
        empty_tracker = PositionTracker()
        return BacktestResult(
            run_id=run_id,
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            trade_log=empty_tracker.to_trade_log(),
            daily_pnl=empty_tracker.to_daily_pnl_series(),
            total_pnl_cents=0,
            total_fees_cents=0,
            settled_contracts=0,
            open_contracts=0,
        )
