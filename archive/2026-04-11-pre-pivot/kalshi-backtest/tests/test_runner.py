"""TDD integration tests for BacktestRunner — full bar-by-bar backtest loop.

Tests written RED-first. Uses an in-memory DuckDB with seeded test data
(2 markets, ~10 candles each, one market settled) and stub strategies.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Any

import duckdb
import pandas as pd
import pytest

from kalshi_backtest.db.repository import MarketRepository
from kalshi_backtest.db.schema import apply_schema
from kalshi_backtest.simulation.protocol import Position, Signal
from kalshi_backtest.simulation.snapshot import MarketSnapshot


# ---------------------------------------------------------------------------
# Stub strategies
# ---------------------------------------------------------------------------

class AlwaysBuyStrategy:
    """Stub strategy: always buys YES at limit 60 if no open position."""

    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]:
        """Buy yes if we have no position on this ticker yet."""
        already_open = any(p.ticker == snapshot.ticker for p in open_positions)
        if already_open:
            return []
        return [
            Signal(
                ticker=snapshot.ticker,
                direction="yes",
                contracts=2,
                limit_price=60,
                reason="always_buy",
            )
        ]


class NeverBuyStrategy:
    """Stub strategy: never generates any signals."""

    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]:
        """Always return empty."""
        return []


class SnapshotCapturingStrategy:
    """Records every snapshot passed to generate_signals for assertion."""

    def __init__(self) -> None:
        self.snapshots: list[MarketSnapshot] = []

    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]:
        self.snapshots.append(snapshot)
        return []


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

# Market A: settled YES at close_time
MARKET_A = {
    "ticker": "TEST-A",
    "event_ticker": "EVT-001",
    "series_ticker": "TEST",
    "subtitle": "Will it happen?",
    "open_time": datetime(2024, 1, 1),
    "close_time": datetime(2024, 1, 15),
    "expiration_time": datetime(2024, 1, 16),
    "status": "settled",
    "result": "yes",
    "ingested_at": datetime(2024, 1, 16),
}

# Market B: settled NO
MARKET_B = {
    "ticker": "TEST-B",
    "event_ticker": "EVT-002",
    "series_ticker": "TEST",
    "subtitle": "Something else?",
    "open_time": datetime(2024, 1, 1),
    "close_time": datetime(2024, 1, 15),
    "expiration_time": datetime(2024, 1, 16),
    "status": "settled",
    "result": "no",
    "ingested_at": datetime(2024, 1, 16),
}

# 10 pre-settlement candles (Jan 5 - Jan 14) + 1 settlement bar (Jan 15 = close_time)
# The settlement bar has ts == close_time, so BarIterator will expose result on that bar.
def _make_candles(ticker: str) -> list[dict]:
    prices = [40, 42, 45, 48, 50, 52, 55, 53, 51, 49, 50]
    return [
        {
            "ticker": ticker,
            "ts": datetime(2024, 1, 5 + i),
            "open_price": prices[i],
            "high_price": prices[i] + 3,
            "low_price": prices[i] - 3,
            "close_price": prices[i],
            "volume": 100 + i * 10,
            "ingested_at": datetime(2024, 1, 16),
        }
        for i in range(11)  # 11 candles: Jan 5 - Jan 15 (Jan 15 == close_time)
    ]


def _seed_db(con: duckdb.DuckDBPyConnection) -> None:
    """Insert test markets and candles into the database."""
    for market in [MARKET_A, MARKET_B]:
        con.execute(
            """
            INSERT INTO markets
                (ticker, event_ticker, series_ticker, subtitle, open_time, close_time,
                 expiration_time, status, result, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                market["ticker"], market["event_ticker"], market["series_ticker"],
                market["subtitle"], market["open_time"], market["close_time"],
                market["expiration_time"], market["status"], market["result"],
                market["ingested_at"],
            ],
        )

    for ticker in ["TEST-A", "TEST-B"]:
        for c in _make_candles(ticker):
            con.execute(
                """
                INSERT INTO candles
                    (ticker, ts, open_price, high_price, low_price, close_price, volume, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [c["ticker"], c["ts"], c["open_price"], c["high_price"],
                 c["low_price"], c["close_price"], c["volume"], c["ingested_at"]],
            )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_con() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with schema + test data seeded."""
    con = duckdb.connect(":memory:")
    apply_schema(con)
    _seed_db(con)
    return con


@pytest.fixture()
def repo(seeded_con: duckdb.DuckDBPyConnection) -> MarketRepository:
    """MarketRepository over seeded in-memory DuckDB."""
    return MarketRepository(seeded_con)


# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------

from kalshi_backtest.simulation.runner import BacktestResult, BacktestRunner


# ---------------------------------------------------------------------------
# Tests: BacktestResult dataclass shape
# ---------------------------------------------------------------------------

class TestBacktestResultShape:
    def test_backtest_result_has_required_fields(self):
        """BacktestResult has all required fields."""
        # Just verify the dataclass fields exist via attribute access
        from dataclasses import fields
        field_names = {f.name for f in fields(BacktestResult)}
        required = {
            "run_id", "strategy_name", "start_date", "end_date",
            "trade_log", "daily_pnl", "total_pnl_cents", "total_fees_cents",
            "settled_contracts", "open_contracts",
        }
        assert required.issubset(field_names)


# ---------------------------------------------------------------------------
# Tests: BacktestRunner.run()
# ---------------------------------------------------------------------------

class TestBacktestRunner:
    def test_runner_produces_backtest_result(self, repo: MarketRepository):
        """runner.run() returns a BacktestResult (no exception)."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=NeverBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert isinstance(result, BacktestResult)

    def test_result_has_trade_log_dataframe(self, repo: MarketRepository):
        """result.trade_log is a pd.DataFrame."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=NeverBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert isinstance(result.trade_log, pd.DataFrame)

    def test_result_has_daily_pnl_series(self, repo: MarketRepository):
        """result.daily_pnl is a pd.Series."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=NeverBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert isinstance(result.daily_pnl, pd.Series)

    def test_result_trade_log_has_required_columns(self, repo: MarketRepository):
        """trade_log has the required columns even when empty."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=NeverBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        required_cols = {"ticker", "direction", "contracts", "entry_price",
                         "entry_ts", "exit_price", "exit_ts", "pnl_cents", "fee_cents"}
        assert required_cols.issubset(set(result.trade_log.columns))

    def test_result_with_buying_strategy_has_trades(self, repo: MarketRepository):
        """AlwaysBuyStrategy produces non-empty trade_log after settlement."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=AlwaysBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert len(result.trade_log) > 0

    def test_result_settled_contracts_positive(self, repo: MarketRepository):
        """settled_contracts > 0 when strategy buys and markets settle."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=AlwaysBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert result.settled_contracts > 0

    def test_result_total_fees_non_negative(self, repo: MarketRepository):
        """total_fees_cents is always >= 0."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=AlwaysBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert result.total_fees_cents >= 0

    def test_result_strategy_name_set(self, repo: MarketRepository):
        """BacktestResult.strategy_name uses the strategy class name."""
        runner = BacktestRunner(repo)
        strategy = NeverBuyStrategy()
        result = runner.run(
            strategy=strategy,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert result.strategy_name == "NeverBuyStrategy"

    def test_result_run_id_is_uuid(self, repo: MarketRepository):
        """run_id is a non-empty UUID string."""
        import uuid
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=NeverBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        # Should parse as valid UUID
        parsed = uuid.UUID(result.run_id)
        assert str(parsed) == result.run_id


# ---------------------------------------------------------------------------
# Tests: No look-ahead possible
# ---------------------------------------------------------------------------

class TestNoLookahead:
    def test_lookahead_not_possible(self, repo: MarketRepository):
        """Snapshots passed to generate_signals never have result set before close_time."""
        capturing = SnapshotCapturingStrategy()
        runner = BacktestRunner(repo)
        runner.run(
            strategy=capturing,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        # For every snapshot where result is not None, ts must be >= close_time
        for snap in capturing.snapshots:
            if snap.result is not None:
                assert snap.ts >= snap.close_time, (
                    f"Look-ahead violation: {snap.ticker} result={snap.result!r} "
                    f"at ts={snap.ts} but close_time={snap.close_time}"
                )


# ---------------------------------------------------------------------------
# Tests: No signals — empty trade log with correct columns
# ---------------------------------------------------------------------------

class TestNoSignals:
    def test_run_with_no_signals_empty_trade_log(self, repo: MarketRepository):
        """NeverBuyStrategy produces empty trade_log with correct columns."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=NeverBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert isinstance(result.trade_log, pd.DataFrame)
        assert len(result.trade_log) == 0
        required = {"ticker", "direction", "contracts", "entry_price",
                    "entry_ts", "exit_price", "exit_ts", "pnl_cents", "fee_cents"}
        assert required.issubset(set(result.trade_log.columns))

    def test_run_with_no_signals_total_pnl_zero(self, repo: MarketRepository):
        """With no signals, total_pnl_cents is 0."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=NeverBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert result.total_pnl_cents == 0

    def test_run_with_no_signals_settled_contracts_zero(self, repo: MarketRepository):
        """With no signals, settled_contracts is 0."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=NeverBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert result.settled_contracts == 0


# ---------------------------------------------------------------------------
# Tests: Date windowing
# ---------------------------------------------------------------------------

class TestDateWindowing:
    def test_run_lookback_window_filters_markets(self, seeded_con: duckdb.DuckDBPyConnection):
        """Passing start_date/end_date that excludes markets returns empty result."""
        # Use a date range that has no markets
        repo = MarketRepository(seeded_con)
        capturing = SnapshotCapturingStrategy()
        runner = BacktestRunner(repo)
        runner.run(
            strategy=capturing,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 1, 31),
        )
        # No snapshots should be produced — no markets in that window
        assert len(capturing.snapshots) == 0

    def test_run_with_series_filter(self, seeded_con: duckdb.DuckDBPyConnection):
        """series_tickers filter limits markets processed."""
        repo = MarketRepository(seeded_con)
        capturing = SnapshotCapturingStrategy()
        runner = BacktestRunner(repo)

        # Add a different-series market to the DB
        seeded_con.execute(
            """
            INSERT INTO markets
                (ticker, event_ticker, series_ticker, subtitle, open_time, close_time,
                 expiration_time, status, result, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                "OTHER-X", "EVT-X", "OTHER", None,
                datetime(2024, 1, 1), datetime(2024, 1, 15),
                datetime(2024, 1, 16), "settled", "yes", datetime(2024, 1, 16),
            ],
        )
        runner.run(
            strategy=capturing,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
            series_tickers=["TEST"],
        )
        # Only TEST-series snapshots should appear
        for snap in capturing.snapshots:
            assert snap.series_ticker == "TEST"


# ---------------------------------------------------------------------------
# Tests: Single-settlement guarantee
# ---------------------------------------------------------------------------

class TestSettlementOnce:
    def test_settlement_triggered_exactly_once_per_ticker(self, repo: MarketRepository):
        """Each market is settled at most once even with multiple post-close bars."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=AlwaysBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        # settled_contracts should equal 2 (AlwaysBuyStrategy buys 2 on each market)
        # TEST-A: 2 contracts bought, settled YES → win
        # TEST-B: 2 contracts bought, settled NO → loss
        # total settled contracts = 4
        assert result.settled_contracts == 4

    def test_open_contracts_zero_after_full_settlement(self, repo: MarketRepository):
        """All contracts are settled — open_contracts is 0."""
        runner = BacktestRunner(repo)
        result = runner.run(
            strategy=AlwaysBuyStrategy(),
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 31),
        )
        assert result.open_contracts == 0
