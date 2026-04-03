"""Tests for polling job: make_poll_tick and _to_orm (DATA-02, DATA-04)."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, call, patch

import pytest

from kalshi_tracker.daemon.warmup import WarmupTracker
from kalshi_tracker.kalshi.client import RateLimitError


# Helper: build a minimal domain MarketSnapshot for tests.
# Import deferred to avoid ImportError if types.py is missing fields.
def _make_domain_snapshot(ticker: str = "TEST-1") -> object:
    from kalshi_tracker.kalshi.types import MarketSnapshot as DomainSnapshot

    return DomainSnapshot(
        ticker=ticker,
        series_ticker="TEST",
        yes_bid=45,
        yes_ask=47,
        no_bid=53,
        no_ask=55,
        last_price=45,
        volume=1000,
        volume_24h=5000,
        status="open",
        captured_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


def _make_mock_session_factory(session: MagicMock) -> MagicMock:
    """Return a session_factory mock whose context manager yields session."""
    factory = MagicMock()
    factory.return_value.__enter__ = MagicMock(return_value=session)
    factory.return_value.__exit__ = MagicMock(return_value=False)
    return factory


def test_poll_tick_calls_client() -> None:
    from kalshi_tracker.daemon.poller import make_poll_tick

    client = MagicMock()
    client.get_politics_markets.return_value = []
    session = MagicMock()
    factory = _make_mock_session_factory(session)
    warmup = WarmupTracker(threshold=60)

    poll_tick = make_poll_tick(client, factory, warmup)
    poll_tick()

    client.get_politics_markets.assert_called_once()


def test_poll_tick_persists_snapshots() -> None:
    from kalshi_tracker.daemon.poller import make_poll_tick

    domain_snap = _make_domain_snapshot("PRES-24-YES-K")
    client = MagicMock()
    client.get_politics_markets.return_value = [domain_snap]
    session = MagicMock()
    factory = _make_mock_session_factory(session)
    warmup = WarmupTracker(threshold=60)

    poll_tick = make_poll_tick(client, factory, warmup)
    poll_tick()

    session.add_all.assert_called_once()
    orm_rows = session.add_all.call_args[0][0]
    assert len(orm_rows) == 1
    session.commit.assert_called_once()


def test_poll_tick_rate_limit() -> None:
    from kalshi_tracker.daemon.poller import make_poll_tick

    client = MagicMock()
    client.get_politics_markets.side_effect = RateLimitError("rate limited")
    session = MagicMock()
    factory = _make_mock_session_factory(session)
    warmup = WarmupTracker(threshold=60)

    poll_tick = make_poll_tick(client, factory, warmup)
    # Must NOT raise — poll_tick catches RateLimitError internally
    poll_tick()

    session.add_all.assert_not_called()


def test_poll_tick_api_error() -> None:
    from kalshi_tracker.daemon.poller import make_poll_tick

    client = MagicMock()
    client.get_politics_markets.side_effect = RuntimeError("network failure")
    session = MagicMock()
    factory = _make_mock_session_factory(session)
    warmup = WarmupTracker(threshold=60)

    poll_tick = make_poll_tick(client, factory, warmup)
    poll_tick()  # must not raise

    session.add_all.assert_not_called()


def test_to_orm_mapping() -> None:
    from kalshi_tracker.daemon.poller import _to_orm
    from kalshi_tracker.db.models import MarketSnapshot as OrmSnapshot

    domain = _make_domain_snapshot("MAP-TEST-1")
    orm = _to_orm(domain)

    assert isinstance(orm, OrmSnapshot)
    assert orm.ticker == "MAP-TEST-1"
    assert orm.yes_bid == 45
    assert orm.volume == 1000
    assert orm.captured_at == datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert orm.raw_snapshot == {}
