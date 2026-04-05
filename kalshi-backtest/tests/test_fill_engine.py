"""TDD tests for FillEngine — fee formula, fill model, and binary P&L.

Verifies:
- Fee formula: ceil(0.07 * C * P * (1-P)) with known values
- Fill price simulation: YES buy fills at mid + half_spread
- P&L: settlement (hold-to-resolution) and exit (mark-to-market)
- Fill dataclass is frozen (immutable)
- FillEngine.try_fill returns Fill or None based on limit price
"""
from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from kalshi_backtest.simulation.fill_engine import (
    Fill,
    FillEngine,
    calculate_exit_pnl,
    calculate_fee_cents,
    calculate_settlement_pnl,
    simulate_fill_price,
)
from kalshi_backtest.simulation.protocol import Position, Signal
from kalshi_backtest.simulation.snapshot import MarketSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

T0 = datetime(2024, 1, 1, 12, 0, 0)


def _snapshot(close_price: int = 55, result: str | None = None) -> MarketSnapshot:
    return MarketSnapshot(
        ticker="TICKER-A",
        event_ticker="EV-TEST",
        series_ticker="SR-TEST",
        ts=T0,
        close_price=close_price,
        close_time=T0,
        result=result,
    )


def _signal(direction: str = "yes", limit_price: int = 60, contracts: int = 10) -> Signal:
    return Signal(
        ticker="TICKER-A",
        direction=direction,
        contracts=contracts,
        limit_price=limit_price,
        reason="test signal",
    )


def _position(
    direction: str = "yes",
    entry_price: int = 40,
    contracts: int = 10,
) -> Position:
    return Position(
        ticker="TICKER-A",
        direction=direction,
        contracts=contracts,
        entry_price=entry_price,
        entry_ts=T0,
        fill_id="test-fill-id",
    )


# ---------------------------------------------------------------------------
# Fee formula tests
# ---------------------------------------------------------------------------


def test_fee_at_50_pct_1_contract() -> None:
    """1 contract at 50%: 0.07 * 1 * 0.5 * 0.5 = 0.0175 → ceil = 1."""
    assert calculate_fee_cents(1, 0.50) == 1


def test_fee_100_contracts_50_pct() -> None:
    """100 contracts at 50%: 0.07 * 100 * 0.5 * 0.5 = 1.75 → ceil = 2."""
    assert calculate_fee_cents(100, 0.50) == 2


def test_fee_at_extreme_price() -> None:
    """10 contracts at 1%: 0.07 * 10 * 0.01 * 0.99 = 0.00693 → ceil = 1 (min floor)."""
    assert calculate_fee_cents(10, 0.01) == 1


def test_fee_at_99_pct() -> None:
    """Symmetric to 1%: 0.07 * 10 * 0.99 * 0.01 = 0.00693 → ceil = 1."""
    assert calculate_fee_cents(10, 0.99) == 1


def test_fee_zero_contracts_raises() -> None:
    """Zero contracts should raise ValueError."""
    with pytest.raises(ValueError, match="contracts must be >= 1"):
        calculate_fee_cents(0, 0.50)


def test_fee_negative_contracts_raises() -> None:
    """Negative contracts should raise ValueError."""
    with pytest.raises(ValueError, match="contracts must be >= 1"):
        calculate_fee_cents(-5, 0.50)


def test_fee_price_above_range_raises() -> None:
    """Price fraction > 1.0 should raise ValueError."""
    with pytest.raises(ValueError, match="price_fraction must be in"):
        calculate_fee_cents(1, 1.5)


def test_fee_price_below_range_raises() -> None:
    """Price fraction < 0.0 should raise ValueError."""
    with pytest.raises(ValueError, match="price_fraction must be in"):
        calculate_fee_cents(1, -0.1)


def test_fee_at_zero_price() -> None:
    """Price fraction = 0.0: 0.07 * 1 * 0 * 1 = 0 → max(1, ceil(0)) = 1."""
    assert calculate_fee_cents(1, 0.0) == 1


def test_fee_at_one_price() -> None:
    """Price fraction = 1.0: 0.07 * 1 * 1 * 0 = 0 → max(1, ceil(0)) = 1."""
    assert calculate_fee_cents(1, 1.0) == 1


# ---------------------------------------------------------------------------
# Fill price simulation tests
# ---------------------------------------------------------------------------


def test_yes_buy_fill_above_mid() -> None:
    """YES buy: fill at mid + ceil(spread_floor/2) = 55 + 1 = 56. limit=60 >= 56 → fills."""
    result = simulate_fill_price("yes", limit_price=60, mid_price=55, spread_floor=1)
    assert result == 56


def test_yes_buy_limit_too_low_returns_none() -> None:
    """YES buy: mid + half_spread = 56, but limit=54 < 56 → no fill."""
    result = simulate_fill_price("yes", limit_price=54, mid_price=55, spread_floor=1)
    assert result is None


def test_yes_buy_limit_exactly_at_ask() -> None:
    """YES buy: limit exactly equals ask price → fills."""
    result = simulate_fill_price("yes", limit_price=56, mid_price=55, spread_floor=1)
    assert result == 56


def test_no_buy_fill_below_mid() -> None:
    """NO buy: yes_ask implied from (100 - fill). Fill at mid - half_spread = 55 - 1 = 54.
    For NO, we're buying NO at 100 - yes_price = 100 - 54 = 46. limit=46 >= 46 → fills."""
    result = simulate_fill_price("no", limit_price=46, mid_price=55, spread_floor=1)
    assert result == 54  # returns fill price in YES terms


def test_no_buy_limit_too_low_returns_none() -> None:
    """NO buy: fill would be at yes_price=54, NO cost = 46. limit=45 < 46 → no fill."""
    result = simulate_fill_price("no", limit_price=45, mid_price=55, spread_floor=1)
    assert result is None


def test_fill_capped_at_100() -> None:
    """YES buy: mid=99 + 1 = 100 → capped at 100. limit=100 >= 100 → fills at 100."""
    result = simulate_fill_price("yes", limit_price=100, mid_price=99, spread_floor=1)
    assert result == 100


def test_fill_floored_at_0() -> None:
    """NO buy: mid=1, ask_yes = 1 - 1 = 0 → floored at 0. limit=100 (NO pays 100) → fills at 0."""
    result = simulate_fill_price("no", limit_price=100, mid_price=1, spread_floor=1)
    assert result == 0  # yes price = 0, NO cost = 100 - 0 = 100


# ---------------------------------------------------------------------------
# Settlement P&L tests
# ---------------------------------------------------------------------------


def test_settlement_yes_win() -> None:
    """YES position wins: (100 - entry) * contracts = (100 - 40) * 10 = 600 cents."""
    assert calculate_settlement_pnl("yes", entry_price=40, contracts=10, result="yes") == 600


def test_settlement_yes_loss() -> None:
    """YES position loses: -entry_price * contracts = -40 * 10 = -400 cents."""
    assert calculate_settlement_pnl("yes", entry_price=40, contracts=10, result="no") == -400


def test_settlement_no_win() -> None:
    """NO position wins (market resolves NO): (100 - entry) * contracts = (100 - 40) * 10 = 600."""
    assert calculate_settlement_pnl("no", entry_price=40, contracts=10, result="no") == 600


def test_settlement_no_loss() -> None:
    """NO position loses (market resolves YES): -entry_price * contracts = -40 * 10 = -400."""
    assert calculate_settlement_pnl("no", entry_price=40, contracts=10, result="yes") == -400


def test_settlement_void_raises() -> None:
    """VOID result should raise ValueError — void handling is BacktestRunner's responsibility."""
    with pytest.raises(ValueError, match="result"):
        calculate_settlement_pnl("yes", entry_price=40, contracts=10, result="void")


# ---------------------------------------------------------------------------
# Exit P&L tests (mark-to-market)
# ---------------------------------------------------------------------------


def test_exit_pnl_yes_profit() -> None:
    """YES exit profit: (exit - entry) * contracts = (60 - 40) * 10 = 200 cents."""
    assert calculate_exit_pnl("yes", entry_price=40, exit_price=60, contracts=10) == 200


def test_exit_pnl_yes_loss() -> None:
    """YES exit loss: (exit - entry) * contracts = (40 - 60) * 10 = -200 cents."""
    assert calculate_exit_pnl("yes", entry_price=60, exit_price=40, contracts=10) == -200


def test_exit_pnl_no_profit() -> None:
    """NO exit profit: exit price is the YES price we receive.
    For NO: profit = (entry_no - exit_no) * contracts = ((100-40) - (100-60)) * 10 = (60-40)*10 = 200."""
    # entry_price=40 means bought NO at 40 cents (yes was at 60)
    # exit_price=20 means sold NO at 20 cents (yes moved to 80)
    assert calculate_exit_pnl("no", entry_price=40, exit_price=20, contracts=10) == 200


def test_exit_pnl_no_loss() -> None:
    """NO exit loss: position moves against us."""
    assert calculate_exit_pnl("no", entry_price=40, exit_price=60, contracts=10) == -200


# ---------------------------------------------------------------------------
# Fill dataclass tests
# ---------------------------------------------------------------------------


def test_fill_is_frozen() -> None:
    """Fill is a frozen dataclass — mutations must raise FrozenInstanceError."""
    fill = Fill(
        fill_id="test-id",
        ticker="TICKER-A",
        direction="yes",
        contracts=10,
        fill_price=56,
        fee_cents=2,
        ts=T0,
        reason="test",
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        fill.contracts = 5  # type: ignore[misc]


def test_fill_fields_accessible() -> None:
    """Fill fields are accessible after construction."""
    fill = Fill(
        fill_id="abc-123",
        ticker="TICKER-B",
        direction="no",
        contracts=5,
        fill_price=44,
        fee_cents=1,
        ts=T0,
        reason="exit signal",
    )
    assert fill.ticker == "TICKER-B"
    assert fill.direction == "no"
    assert fill.contracts == 5
    assert fill.fill_price == 44


# ---------------------------------------------------------------------------
# FillEngine.try_fill integration tests
# ---------------------------------------------------------------------------


def test_try_fill_yes_buy_success() -> None:
    """FillEngine.try_fill returns Fill when limit_price >= fill_price."""
    engine = FillEngine(spread_floor=1)
    signal = _signal(direction="yes", limit_price=60)
    snapshot = _snapshot(close_price=55)

    fill = engine.try_fill(signal, snapshot)

    assert fill is not None
    assert fill.direction == "yes"
    assert fill.fill_price == 56  # mid(55) + half_spread(1)
    assert fill.contracts == 10
    assert fill.ticker == "TICKER-A"
    assert fill.fee_cents >= 1


def test_try_fill_returns_none_when_not_fillable() -> None:
    """FillEngine.try_fill returns None when limit_price < fill_price."""
    engine = FillEngine(spread_floor=1)
    signal = _signal(direction="yes", limit_price=50)  # limit < mid+half_spread=56
    snapshot = _snapshot(close_price=55)

    fill = engine.try_fill(signal, snapshot)

    assert fill is None


def test_try_fill_has_unique_fill_id() -> None:
    """Each fill gets a unique fill_id (uuid4 string)."""
    engine = FillEngine(spread_floor=1)
    signal = _signal(direction="yes", limit_price=60)
    snapshot = _snapshot(close_price=55)

    fill1 = engine.try_fill(signal, snapshot)
    fill2 = engine.try_fill(signal, snapshot)

    assert fill1 is not None
    assert fill2 is not None
    assert fill1.fill_id != fill2.fill_id


# ---------------------------------------------------------------------------
# FillEngine.close_position tests
# ---------------------------------------------------------------------------


def test_close_position_yes() -> None:
    """close_position creates a closing fill in opposite direction at current market price."""
    engine = FillEngine(spread_floor=1)
    pos = _position(direction="yes", entry_price=40)
    snapshot = _snapshot(close_price=60)

    fill = engine.close_position(pos, snapshot)

    assert fill is not None
    # Closing a YES position is a YES sell — fills at mid - half_spread = 60 - 1 = 59
    assert fill.direction == "yes"
    assert fill.contracts == 10
    assert fill.ticker == "TICKER-A"


def test_close_position_no() -> None:
    """close_position creates closing fill for NO position."""
    engine = FillEngine(spread_floor=1)
    pos = _position(direction="no", entry_price=40)
    snapshot = _snapshot(close_price=40)

    fill = engine.close_position(pos, snapshot)

    assert fill is not None
    assert fill.direction == "no"
    assert fill.contracts == 10
