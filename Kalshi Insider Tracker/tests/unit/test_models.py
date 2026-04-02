"""Tests for ORM models — LOG-03 (append-only enforcement).

All tests are skipped until Plan 02 implements the database models.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="ORM models not yet implemented — Plan 02")


def test_signal_is_append_only() -> None:
    """LOG-03: Signal model has no update() or delete() methods exposed."""
    pytest.fail("Not yet implemented")


def test_trade_is_append_only() -> None:
    """LOG-03: Trade model has no update() or delete() methods exposed."""
    pytest.fail("Not yet implemented")


def test_market_snapshot_is_append_only() -> None:
    """LOG-03: MarketSnapshot model has no update() or delete() methods exposed."""
    pytest.fail("Not yet implemented")


def test_market_entity_is_mutable() -> None:
    """Market entity table (metadata) is NOT append-only — it is updated on upsert."""
    pytest.fail("Not yet implemented")
