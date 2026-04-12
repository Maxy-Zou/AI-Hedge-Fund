"""RED test scaffold for kalshi_backtest.strategies module.

These tests import from modules that do not yet exist. They will fail with
ImportError until Plans 04-02 and 04-03 create the implementation files.

Covers requirements:
    STRAT-01: InsiderTrackerAdapter — reads signals from Insider Tracker DB
    STRAT-02: ExampleStrategy — simple threshold-based buy strategy
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from types import SimpleNamespace

import pytest

# These imports will fail RED until Plan 04-02/04-03 creates the strategy modules.
from kalshi_backtest.strategies.insider_tracker import InsiderTrackerAdapter  # noqa: F401
from kalshi_backtest.strategies.example import ExampleStrategy  # noqa: F401

from kalshi_backtest.simulation.protocol import Position, Signal, Strategy
from tests.conftest import insert_signal_row


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(
    ticker: str = "KXBTC-24DEC-T50000",
    ts: datetime | None = None,
    close_price: int = 40,
) -> SimpleNamespace:
    """Build a minimal MarketSnapshot-like object via SimpleNamespace.

    Uses SimpleNamespace so tests don't need to import the real MarketSnapshot
    and trigger any transitional import errors in the simulation layer.

    Args:
        ticker: Kalshi market ticker string.
        ts: Bar timestamp (naive UTC). Defaults to 2024-01-10T14:00:00.
        close_price: Yes price at bar close in cents [0, 100].

    Returns:
        SimpleNamespace with .ticker, .ts, and .close_price attributes.
    """
    return SimpleNamespace(
        ticker=ticker,
        ts=ts or datetime(2024, 1, 10, 14, 0, 0),
        close_price=close_price,
    )


def _make_position(ticker: str) -> Position:
    """Build a minimal open Position for use in open_positions lists.

    Args:
        ticker: Kalshi market ticker held in this position.

    Returns:
        Frozen Position object.
    """
    return Position(
        ticker=ticker,
        direction="yes",
        contracts=1,
        entry_price=40,
        entry_ts=datetime(2024, 1, 10, 12, 0, 0),
        fill_id="fill-001",
    )


# ---------------------------------------------------------------------------
# STRAT-01: InsiderTrackerAdapter tests
# ---------------------------------------------------------------------------


def test_insider_adapter_generates_signal(sqlite_signals_db: tuple[str, sqlite3.Connection]) -> None:
    """STRAT-01: Signal row in DB earlier than snapshot.ts → Signal returned.

    The adapter must query signals where detected_at < snapshot.ts and the
    ticker matches. A matching row produces a Signal with the correct ticker
    and a valid direction.
    """
    db_url, conn = sqlite_signals_db
    insert_signal_row(conn, ticker="KXBTC-24DEC-T50000", detected_at="2024-01-10T12:00:00")

    adapter = InsiderTrackerAdapter(db_url=db_url)
    snapshot = _make_snapshot(ticker="KXBTC-24DEC-T50000", ts=datetime(2024, 1, 10, 14, 0, 0))
    signals = adapter.generate_signals(snapshot, open_positions=[])

    assert len(signals) == 1
    sig = signals[0]
    assert isinstance(sig, Signal)
    assert sig.ticker == "KXBTC-24DEC-T50000"
    assert sig.direction in ("yes", "no")
    assert sig.contracts >= 1


def test_insider_adapter_no_lookahead(sqlite_signals_db: tuple[str, sqlite3.Connection]) -> None:
    """STRAT-01: Signal at exactly snapshot.ts is excluded (strictly <, not <=).

    Lookahead prevention: a signal detected at the same moment as the bar
    timestamp must NOT be returned, since the strategy could not have known
    about it at that instant.
    """
    db_url, conn = sqlite_signals_db
    # detected_at == snapshot.ts exactly
    insert_signal_row(conn, ticker="KXBTC-24DEC-T50000", detected_at="2024-01-10T14:00:00")

    adapter = InsiderTrackerAdapter(db_url=db_url)
    snapshot = _make_snapshot(ticker="KXBTC-24DEC-T50000", ts=datetime(2024, 1, 10, 14, 0, 0))
    signals = adapter.generate_signals(snapshot, open_positions=[])

    assert signals == []


def test_insider_adapter_no_signals(sqlite_signals_db: tuple[str, sqlite3.Connection]) -> None:
    """STRAT-01: Empty signals table → returns empty list (no error)."""
    db_url, conn = sqlite_signals_db
    # No rows inserted

    adapter = InsiderTrackerAdapter(db_url=db_url)
    snapshot = _make_snapshot()
    signals = adapter.generate_signals(snapshot, open_positions=[])

    assert signals == []


def test_insider_adapter_skips_held(sqlite_signals_db: tuple[str, sqlite3.Connection]) -> None:
    """STRAT-01: Ticker already in open_positions → no new signal generated.

    Avoids pyramiding into an existing position on the same ticker.
    """
    db_url, conn = sqlite_signals_db
    insert_signal_row(conn, ticker="KXBTC-24DEC-T50000", detected_at="2024-01-10T12:00:00")

    adapter = InsiderTrackerAdapter(db_url=db_url)
    snapshot = _make_snapshot(ticker="KXBTC-24DEC-T50000")
    open_positions = [_make_position("KXBTC-24DEC-T50000")]
    signals = adapter.generate_signals(snapshot, open_positions=open_positions)

    assert signals == []


def test_insider_adapter_db_error() -> None:
    """STRAT-01: Bad DB URL → returns [], logs warning, does not raise.

    The adapter must be resilient to database connectivity issues. A bad URL
    should result in an empty signal list, not a crash.
    """
    adapter = InsiderTrackerAdapter(db_url="sqlite:///nonexistent/path/that/does/not/exist.db")
    snapshot = _make_snapshot()
    signals = adapter.generate_signals(snapshot, open_positions=[])

    assert signals == []


def test_insider_adapter_confidence_filter(sqlite_signals_db: tuple[str, sqlite3.Connection]) -> None:
    """STRAT-01: Signal with confidence below threshold is filtered out.

    Low-confidence signals (below the adapter's minimum threshold) must not
    produce trading signals.
    """
    db_url, conn = sqlite_signals_db
    # Insert a low-confidence signal (0.1) and a high-confidence one (0.9)
    insert_signal_row(conn, ticker="KXBTC-24DEC-T50000", confidence=0.1, detected_at="2024-01-10T12:00:00")
    insert_signal_row(conn, ticker="KXBTC-24DEC-T50001", confidence=0.9, detected_at="2024-01-10T12:00:00")

    adapter = InsiderTrackerAdapter(db_url=db_url, min_confidence=0.5)
    # Use a snapshot for the low-confidence ticker — should return nothing
    snapshot = _make_snapshot(ticker="KXBTC-24DEC-T50000", ts=datetime(2024, 1, 10, 14, 0, 0))
    signals = adapter.generate_signals(snapshot, open_positions=[])

    assert signals == []


# ---------------------------------------------------------------------------
# STRAT-02: ExampleStrategy tests
# ---------------------------------------------------------------------------


def test_example_strategy_buys_cheap() -> None:
    """STRAT-02: close_price below threshold → Signal with direction='yes' returned."""
    strategy = ExampleStrategy(buy_threshold=40)
    snapshot = _make_snapshot(close_price=30)
    signals = strategy.generate_signals(snapshot, open_positions=[])

    assert len(signals) == 1
    sig = signals[0]
    assert isinstance(sig, Signal)
    assert sig.direction == "yes"


def test_example_strategy_skips_expensive() -> None:
    """STRAT-02: close_price at or above threshold → returns empty list."""
    strategy = ExampleStrategy(buy_threshold=40)
    snapshot = _make_snapshot(close_price=50)
    signals = strategy.generate_signals(snapshot, open_positions=[])

    assert signals == []


def test_example_strategy_at_threshold() -> None:
    """STRAT-02: close_price exactly equal to threshold → returns empty list.

    The condition must be strictly less-than, not less-than-or-equal.
    """
    strategy = ExampleStrategy(buy_threshold=40)
    snapshot = _make_snapshot(close_price=40)
    signals = strategy.generate_signals(snapshot, open_positions=[])

    assert signals == []


def test_example_strategy_skips_held() -> None:
    """STRAT-02: Ticker already in open_positions → no new signal generated."""
    strategy = ExampleStrategy(buy_threshold=40)
    snapshot = _make_snapshot(ticker="KXBTC-24DEC-T50000", close_price=30)
    open_positions = [_make_position("KXBTC-24DEC-T50000")]
    signals = strategy.generate_signals(snapshot, open_positions=open_positions)

    assert signals == []


def test_example_strategy_satisfies_protocol() -> None:
    """STRAT-02: ExampleStrategy() is an instance of the Strategy protocol.

    Confirms structural subtyping — ExampleStrategy doesn't need to inherit
    Strategy; it just needs to implement generate_signals().
    """
    strategy = ExampleStrategy()
    assert isinstance(strategy, Strategy)
