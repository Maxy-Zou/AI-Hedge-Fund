"""TDD tests for PositionTracker — open/close/settle position lifecycle.

Tests written RED-first before any implementation exists.
"""
from __future__ import annotations

from datetime import datetime, date

import pandas as pd
import pytest

from kalshi_backtest.simulation.fill_engine import Fill
from kalshi_backtest.simulation.protocol import Position


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_fill(
    ticker: str = "MKT-A",
    direction: str = "yes",
    contracts: int = 5,
    fill_price: int = 40,
    fill_id: str = "fill-001",
    ts: datetime | None = None,
    reason: str = "test_signal",
) -> Fill:
    """Create a Fill for testing."""
    return Fill(
        fill_id=fill_id,
        ticker=ticker,
        direction=direction,
        contracts=contracts,
        fill_price=fill_price,
        fee_cents=2,
        ts=ts or datetime(2024, 1, 10, 12, 0, 0),
        reason=reason,
    )


def make_position(
    ticker: str = "MKT-A",
    direction: str = "yes",
    contracts: int = 5,
    entry_price: int = 40,
    fill_id: str = "fill-001",
    entry_ts: datetime | None = None,
) -> Position:
    """Create a Position for testing."""
    return Position(
        ticker=ticker,
        direction=direction,
        contracts=contracts,
        entry_price=entry_price,
        entry_ts=entry_ts or datetime(2024, 1, 10, 12, 0, 0),
        fill_id=fill_id,
    )


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from kalshi_backtest.simulation.position_tracker import ClosedPosition, PositionTracker


# ---------------------------------------------------------------------------
# Test: Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_no_positions_initially(self):
        """Fresh tracker has no open or closed positions."""
        tracker = PositionTracker()
        assert tracker.open_positions == []

    def test_no_closed_positions_initially(self):
        """Fresh tracker has no closed positions."""
        tracker = PositionTracker()
        assert tracker.closed_positions == []


# ---------------------------------------------------------------------------
# Test: open() from Fill
# ---------------------------------------------------------------------------

class TestOpenPosition:
    def test_open_position_from_fill(self):
        """tracker.open(fill) creates and stores a Position."""
        tracker = PositionTracker()
        fill = make_fill()
        pos = tracker.open(fill)

        assert isinstance(pos, Position)
        assert tracker.open_positions == [pos]

    def test_open_position_fields_match_fill(self):
        """Position created from fill has matching fields."""
        tracker = PositionTracker()
        fill = make_fill(
            ticker="AAPL-2024",
            direction="no",
            contracts=3,
            fill_price=60,
            fill_id="f-xyz",
        )
        pos = tracker.open(fill)

        assert pos.ticker == "AAPL-2024"
        assert pos.direction == "no"
        assert pos.contracts == 3
        assert pos.entry_price == 60
        assert pos.fill_id == "f-xyz"

    def test_open_multiple_positions_same_ticker(self):
        """Multiple fills on same ticker both appear in open_positions."""
        tracker = PositionTracker()
        f1 = make_fill(fill_id="f-001")
        f2 = make_fill(fill_id="f-002")
        tracker.open(f1)
        tracker.open(f2)

        assert len(tracker.open_positions) == 2

    def test_open_positions_across_tickers(self):
        """Open positions on different tickers both tracked."""
        tracker = PositionTracker()
        tracker.open(make_fill(ticker="MKT-A", fill_id="f-001"))
        tracker.open(make_fill(ticker="MKT-B", fill_id="f-002"))

        tickers = {p.ticker for p in tracker.open_positions}
        assert tickers == {"MKT-A", "MKT-B"}


# ---------------------------------------------------------------------------
# Test: close() via fill
# ---------------------------------------------------------------------------

class TestClosePosition:
    def test_close_position_moves_to_closed(self):
        """After close(), position is in closed_positions and not open_positions."""
        tracker = PositionTracker()
        fill = make_fill()
        pos = tracker.open(fill)

        close_fill = make_fill(
            fill_id="f-close",
            fill_price=70,
            ts=datetime(2024, 1, 11, 12, 0, 0),
        )
        tracker.close(pos, close_fill)

        assert tracker.open_positions == []
        assert len(tracker.closed_positions) == 1

    def test_close_position_has_correct_exit_price(self):
        """ClosedPosition records exit fill price."""
        tracker = PositionTracker()
        pos = tracker.open(make_fill(fill_price=40))
        close_fill = make_fill(fill_id="f-close", fill_price=65)
        closed = tracker.close(pos, close_fill)

        assert closed.exit_price == 65

    def test_close_position_yes_pnl(self):
        """YES position close: pnl = (exit - entry) * contracts."""
        tracker = PositionTracker()
        pos = tracker.open(make_fill(direction="yes", fill_price=40, contracts=5))
        close_fill = make_fill(fill_id="f-close", fill_price=65, direction="yes")
        closed = tracker.close(pos, close_fill)

        # (65 - 40) * 5 = 125
        assert closed.pnl_cents == 125

    def test_close_returns_closed_position(self):
        """close() returns the ClosedPosition object."""
        tracker = PositionTracker()
        pos = tracker.open(make_fill())
        close_fill = make_fill(fill_id="f-close", fill_price=50)
        result = tracker.close(pos, close_fill)
        assert isinstance(result, ClosedPosition)


# ---------------------------------------------------------------------------
# Test: settle() — settlement by result
# ---------------------------------------------------------------------------

class TestSettlePositions:
    def test_settle_open_positions_for_ticker(self):
        """settle() settles all open positions for named ticker."""
        tracker = PositionTracker()
        tracker.open(make_fill(ticker="MKT-A", fill_id="f-001"))
        tracker.open(make_fill(ticker="MKT-A", fill_id="f-002"))

        ts = datetime(2024, 1, 20, 16, 0, 0)
        closed = tracker.settle("MKT-A", result="yes", ts=ts)

        assert len(closed) == 2
        assert tracker.open_positions == []

    def test_settle_only_settles_named_ticker(self):
        """settle() on 'A' does not touch open positions on 'B'."""
        tracker = PositionTracker()
        tracker.open(make_fill(ticker="MKT-A", fill_id="f-001"))
        tracker.open(make_fill(ticker="MKT-B", fill_id="f-002"))

        tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20))

        open_tickers = {p.ticker for p in tracker.open_positions}
        assert open_tickers == {"MKT-B"}

    def test_settle_yes_win_pnl(self):
        """YES position wins on 'yes' result: pnl = (100 - entry) * contracts."""
        tracker = PositionTracker()
        tracker.open(make_fill(direction="yes", fill_price=40, contracts=5, fill_id="f-001"))

        closed_list = tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20))

        # (100 - 40) * 5 = 300
        assert closed_list[0].pnl_cents == 300

    def test_settle_yes_loss_pnl(self):
        """YES position loses on 'no' result: pnl = -entry * contracts."""
        tracker = PositionTracker()
        tracker.open(make_fill(direction="yes", fill_price=40, contracts=5, fill_id="f-001"))

        closed_list = tracker.settle("MKT-A", result="no", ts=datetime(2024, 1, 20))

        # -40 * 5 = -200
        assert closed_list[0].pnl_cents == -200

    def test_settle_no_win_pnl(self):
        """NO position wins on 'no' result: pnl = (100 - entry) * contracts."""
        tracker = PositionTracker()
        tracker.open(make_fill(direction="no", fill_price=60, contracts=3, fill_id="f-001"))

        closed_list = tracker.settle("MKT-A", result="no", ts=datetime(2024, 1, 20))

        # (100 - 60) * 3 = 120
        assert closed_list[0].pnl_cents == 120

    def test_settle_empty_ticker_returns_empty_list(self):
        """settle() on ticker with no open positions returns []."""
        tracker = PositionTracker()
        result = tracker.settle("NONEXISTENT", result="yes", ts=datetime(2024, 1, 20))
        assert result == []

    def test_settle_moves_to_closed_positions(self):
        """Settled positions appear in closed_positions."""
        tracker = PositionTracker()
        tracker.open(make_fill(ticker="MKT-A", fill_id="f-001"))
        tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20))

        assert len(tracker.closed_positions) == 1


# ---------------------------------------------------------------------------
# Test: ClosedPosition dataclass
# ---------------------------------------------------------------------------

class TestClosedPosition:
    def test_closed_position_has_pnl(self):
        """ClosedPosition.pnl_cents is set after settle."""
        tracker = PositionTracker()
        tracker.open(make_fill(direction="yes", fill_price=30, contracts=10, fill_id="f-001"))
        closed_list = tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20))

        # (100 - 30) * 10 = 700
        assert closed_list[0].pnl_cents == 700

    def test_closed_position_has_fee_cents(self):
        """ClosedPosition.fee_cents is carried from fill."""
        tracker = PositionTracker()
        fill = make_fill(fill_id="f-001")
        tracker.open(fill)
        closed_list = tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20))

        assert closed_list[0].fee_cents == fill.fee_cents

    def test_closed_position_exit_reason_settlement(self):
        """Settlement-closed position has exit_reason='settlement'."""
        tracker = PositionTracker()
        tracker.open(make_fill(fill_id="f-001"))
        closed_list = tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20))

        assert closed_list[0].exit_reason == "settlement"


# ---------------------------------------------------------------------------
# Test: to_trade_log() DataFrame
# ---------------------------------------------------------------------------

class TestTradeLog:
    def test_to_trade_log_dataframe_columns(self):
        """to_trade_log() returns DataFrame with required columns."""
        tracker = PositionTracker()
        tracker.open(make_fill(fill_id="f-001"))
        tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20))

        df = tracker.to_trade_log()

        assert isinstance(df, pd.DataFrame)
        required_cols = {
            "ticker", "direction", "contracts",
            "entry_price", "entry_ts", "exit_price", "exit_ts",
            "pnl_cents", "fee_cents", "exit_reason",
        }
        assert required_cols.issubset(set(df.columns))

    def test_to_trade_log_empty_returns_dataframe(self):
        """Empty tracker returns empty DataFrame with correct columns."""
        tracker = PositionTracker()
        df = tracker.to_trade_log()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_to_trade_log_row_count(self):
        """Each closed position is one row in the trade log."""
        tracker = PositionTracker()
        tracker.open(make_fill(ticker="MKT-A", fill_id="f-001"))
        tracker.open(make_fill(ticker="MKT-A", fill_id="f-002"))
        tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20))

        df = tracker.to_trade_log()
        assert len(df) == 2


# ---------------------------------------------------------------------------
# Test: to_daily_pnl_series()
# ---------------------------------------------------------------------------

class TestDailyPnlSeries:
    def test_daily_pnl_series_returns_series(self):
        """to_daily_pnl_series() returns pd.Series."""
        tracker = PositionTracker()
        tracker.open(make_fill(fill_id="f-001"))
        tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20))

        series = tracker.to_daily_pnl_series()
        assert isinstance(series, pd.Series)

    def test_daily_pnl_series_date_index(self):
        """Series index contains date objects."""
        tracker = PositionTracker()
        tracker.open(make_fill(fill_id="f-001"))
        tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20))

        series = tracker.to_daily_pnl_series()
        assert len(series) > 0
        assert isinstance(series.index[0], date)

    def test_daily_pnl_series_sums_per_day(self):
        """Multiple settlements on same day are summed."""
        tracker = PositionTracker()
        # Two positions, both settled on Jan 20
        tracker.open(make_fill(fill_id="f-001", fill_price=40, contracts=5))
        tracker.open(make_fill(fill_id="f-002", fill_price=30, contracts=2))
        tracker.settle("MKT-A", result="yes", ts=datetime(2024, 1, 20, 16, 0, 0))

        series = tracker.to_daily_pnl_series()
        # f-001: (100-40)*5 = 300; f-002: (100-30)*2 = 140 → total 440
        assert series[date(2024, 1, 20)] == 440

    def test_daily_pnl_empty_returns_empty_series(self):
        """Empty tracker returns empty Series."""
        tracker = PositionTracker()
        series = tracker.to_daily_pnl_series()
        assert isinstance(series, pd.Series)
        assert len(series) == 0
