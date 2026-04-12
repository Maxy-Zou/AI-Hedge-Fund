"""TDD tests for simulation type contracts: Strategy Protocol, Signal, Position, MarketSnapshot.

Tests follow the RED → GREEN pattern:
- Task 1 tests cover Strategy Protocol structural subtyping, Signal, and Position.
- Task 2 tests cover MarketSnapshot look-ahead firewall semantics.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Task 1 imports (RED — these will fail until protocol.py is created)
# ---------------------------------------------------------------------------
from kalshi_backtest.simulation.protocol import Position, Signal, Strategy


# ---------------------------------------------------------------------------
# Strategy Protocol tests
# ---------------------------------------------------------------------------


class _ValidStrategy:
    """Minimal class that satisfies the Strategy protocol structurally."""

    def generate_signals(self, snapshot, open_positions):
        return []


class _MissingMethodStrategy:
    """Class that does NOT implement generate_signals — should fail Protocol check."""

    def do_something_else(self):
        pass


def test_strategy_protocol_satisfied_without_inheritance():
    """A class with generate_signals() satisfies Strategy without inheriting from it."""
    obj = _ValidStrategy()
    assert isinstance(obj, Strategy)


def test_strategy_protocol_not_satisfied_missing_method():
    """A class without generate_signals() fails the isinstance() check."""
    obj = _MissingMethodStrategy()
    assert not isinstance(obj, Strategy)


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------


def test_signal_is_frozen():
    """Signal mutation raises an error — model must be frozen."""
    sig = Signal(ticker="KXBTC-24DEC-T50000", direction="yes", contracts=2, limit_price=55, reason="test")
    with pytest.raises((AttributeError, ValidationError, TypeError)):
        sig.ticker = "OTHER"  # type: ignore[misc]


def test_signal_direction_yes_accepted():
    """Signal accepts 'yes' as direction."""
    sig = Signal(ticker="X", direction="yes", contracts=1, limit_price=50, reason="r")
    assert sig.direction == "yes"


def test_signal_direction_no_accepted():
    """Signal accepts 'no' as direction."""
    sig = Signal(ticker="X", direction="no", contracts=1, limit_price=50, reason="r")
    assert sig.direction == "no"


def test_signal_direction_validation():
    """Signal with direction='invalid' raises ValidationError."""
    with pytest.raises(ValidationError):
        Signal(ticker="X", direction="invalid", contracts=1, limit_price=50, reason="r")  # type: ignore[arg-type]


def test_signal_contracts_minimum_one():
    """Signal.contracts must be >= 1."""
    with pytest.raises(ValidationError):
        Signal(ticker="X", direction="yes", contracts=0, limit_price=50, reason="r")


def test_signal_limit_price_low_bound():
    """Signal.limit_price must be >= 0."""
    with pytest.raises(ValidationError):
        Signal(ticker="X", direction="yes", contracts=1, limit_price=-1, reason="r")


def test_signal_limit_price_high_bound():
    """Signal.limit_price must be <= 100."""
    with pytest.raises(ValidationError):
        Signal(ticker="X", direction="yes", contracts=1, limit_price=101, reason="r")


def test_signal_limit_price_boundary_values():
    """Signal accepts limit_price at boundaries 0 and 100."""
    sig_low = Signal(ticker="X", direction="yes", contracts=1, limit_price=0, reason="r")
    sig_high = Signal(ticker="X", direction="yes", contracts=1, limit_price=100, reason="r")
    assert sig_low.limit_price == 0
    assert sig_high.limit_price == 100


# ---------------------------------------------------------------------------
# Position tests
# ---------------------------------------------------------------------------

_ENTRY_TS = datetime(2024, 1, 15, 12, 0, 0)


def test_position_is_frozen():
    """Position mutation raises — model must be frozen."""
    pos = Position(
        ticker="X",
        direction="yes",
        contracts=1,
        entry_price=55,
        entry_ts=_ENTRY_TS,
        fill_id="fill-001",
    )
    with pytest.raises((AttributeError, ValidationError, TypeError)):
        pos.contracts = 5  # type: ignore[misc]


def test_position_fields_present():
    """Position has all required fields: ticker, direction, contracts, entry_price, entry_ts, fill_id."""
    pos = Position(
        ticker="KXBTC-24DEC-T50000",
        direction="no",
        contracts=3,
        entry_price=42,
        entry_ts=_ENTRY_TS,
        fill_id="fill-42",
    )
    assert pos.ticker == "KXBTC-24DEC-T50000"
    assert pos.direction == "no"
    assert pos.contracts == 3
    assert pos.entry_price == 42
    assert pos.entry_ts == _ENTRY_TS
    assert pos.fill_id == "fill-42"


def test_position_direction_validation():
    """Position direction must be 'yes' or 'no'."""
    with pytest.raises(ValidationError):
        Position(
            ticker="X",
            direction="maybe",  # type: ignore[arg-type]
            contracts=1,
            entry_price=50,
            entry_ts=_ENTRY_TS,
            fill_id="f",
        )


def test_position_contracts_minimum_one():
    """Position.contracts must be >= 1."""
    with pytest.raises(ValidationError):
        Position(
            ticker="X",
            direction="yes",
            contracts=0,
            entry_price=50,
            entry_ts=_ENTRY_TS,
            fill_id="f",
        )


def test_position_entry_price_range():
    """Position.entry_price must be in [0, 100]."""
    with pytest.raises(ValidationError):
        Position(
            ticker="X",
            direction="yes",
            contracts=1,
            entry_price=105,
            entry_ts=_ENTRY_TS,
            fill_id="f",
        )


# ---------------------------------------------------------------------------
# Task 2 imports (RED — these will fail until snapshot.py is created)
# ---------------------------------------------------------------------------
from kalshi_backtest.simulation.snapshot import MarketSnapshot, build_snapshot  # noqa: E402

# ---------------------------------------------------------------------------
# Helper dicts for build_snapshot tests
# ---------------------------------------------------------------------------

_CLOSE_TIME = datetime(2024, 6, 1, 20, 0, 0)  # naive UTC


def _market_dict(result: str | None = None) -> dict:
    return {
        "ticker": "KXBTC-24JUN-T60000",
        "event_ticker": "KXBTC-24JUN",
        "series_ticker": "KXBTC",
        "subtitle": "Bitcoin above $60k on June 1, 2024",
        "close_time": _CLOSE_TIME,
        "result": result,
    }


def _candle_dict(ts_offset_days: int = 0) -> dict:
    return {
        "ts": _CLOSE_TIME + timedelta(days=ts_offset_days),
        "close_price": 62,
        "open_price": 58,
        "high_price": 65,
        "low_price": 55,
        "volume": 100,
    }


# ---------------------------------------------------------------------------
# MarketSnapshot tests
# ---------------------------------------------------------------------------


def test_snapshot_result_none_when_suppress_result_true():
    """build_snapshot with suppress_result=True hides result even if DB value is 'yes'."""
    snap = build_snapshot(_market_dict(result="yes"), _candle_dict(ts_offset_days=0), suppress_result=True)
    assert snap.result is None


def test_snapshot_result_visible_when_suppress_result_false():
    """build_snapshot with suppress_result=False exposes result='yes' when present."""
    snap = build_snapshot(_market_dict(result="yes"), _candle_dict(ts_offset_days=0), suppress_result=False)
    assert snap.result == "yes"


def test_snapshot_result_none_when_db_has_none():
    """build_snapshot with suppress_result=False and no result → result is None."""
    snap = build_snapshot(_market_dict(result=None), _candle_dict(ts_offset_days=0), suppress_result=False)
    assert snap.result is None


def test_snapshot_is_frozen():
    """MarketSnapshot mutation raises — model must be frozen."""
    snap = build_snapshot(_market_dict(), _candle_dict(), suppress_result=False)
    with pytest.raises((AttributeError, ValidationError, TypeError)):
        snap.close_price = 99  # type: ignore[misc]


def test_snapshot_close_price_range_low():
    """close_price below 0 raises ValidationError."""
    with pytest.raises(ValidationError):
        MarketSnapshot(
            ticker="X",
            event_ticker="E",
            series_ticker="S",
            ts=datetime(2024, 1, 1),
            close_price=-1,
            close_time=datetime(2024, 1, 2),
        )


def test_snapshot_close_price_range_high():
    """close_price above 100 raises ValidationError."""
    with pytest.raises(ValidationError):
        MarketSnapshot(
            ticker="X",
            event_ticker="E",
            series_ticker="S",
            ts=datetime(2024, 1, 1),
            close_price=101,
            close_time=datetime(2024, 1, 2),
        )


def test_snapshot_build_from_market_and_candle():
    """build_snapshot assembles correct MarketSnapshot from market and candle dicts."""
    market = _market_dict(result="yes")
    candle = _candle_dict(ts_offset_days=-1)
    snap = build_snapshot(market, candle, suppress_result=False)

    assert snap.ticker == "KXBTC-24JUN-T60000"
    assert snap.event_ticker == "KXBTC-24JUN"
    assert snap.series_ticker == "KXBTC"
    assert snap.close_price == 62
    assert snap.open_price == 58
    assert snap.high_price == 65
    assert snap.low_price == 55
    assert snap.volume == 100
    assert snap.result == "yes"


def test_snapshot_datetime_fields_naive_utc():
    """Datetime fields on MarketSnapshot are stored as naive UTC (no tzinfo)."""
    aware_close = _CLOSE_TIME.replace(tzinfo=timezone.utc)
    market = {
        "ticker": "X",
        "event_ticker": "E",
        "series_ticker": "S",
        "close_time": aware_close,
        "result": None,
    }
    candle = {
        "ts": datetime(2024, 5, 31, 0, 0, 0, tzinfo=timezone.utc),
        "close_price": 50,
    }
    snap = build_snapshot(market, candle, suppress_result=False)
    assert snap.ts.tzinfo is None
    assert snap.close_time.tzinfo is None
