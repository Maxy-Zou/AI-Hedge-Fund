"""Unit tests for ai_hedge_fund.db.dates.normalise_as_of.

This helper is the single chokepoint every temporal ``as_of_date <= target``
comparison flows through (memory recall, risk portfolio, paper trading).
It was promoted from two byte-identical private copies in Phase 9 (D6b).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from ai_hedge_fund.db.dates import normalise_as_of


def test_aware_datetime_is_returned_unchanged() -> None:
    aware = datetime(2026, 4, 18, 15, 30, tzinfo=UTC)
    assert normalise_as_of(aware) == aware
    assert normalise_as_of(aware).tzinfo is UTC


def test_naive_datetime_is_treated_as_utc() -> None:
    naive = datetime(2026, 4, 18, 15, 30)
    out = normalise_as_of(naive)
    assert out == datetime(2026, 4, 18, 15, 30, tzinfo=UTC)
    assert out.tzinfo is UTC


def test_date_becomes_midnight_utc() -> None:
    out = normalise_as_of(date(2026, 4, 18))
    assert out == datetime(2026, 4, 18, 0, 0, tzinfo=UTC)


def test_iso_string_without_offset_is_utc() -> None:
    assert normalise_as_of("2026-04-18") == datetime(2026, 4, 18, tzinfo=UTC)
    assert normalise_as_of("2026-04-18T09:00:00") == datetime(2026, 4, 18, 9, tzinfo=UTC)


def test_iso_string_with_offset_preserves_offset() -> None:
    out = normalise_as_of("2026-04-18T09:00:00+05:00")
    assert out.utcoffset() == timedelta(hours=5)
    # Same instant as 04:00 UTC.
    assert out == datetime(2026, 4, 18, 4, 0, tzinfo=UTC)


def test_all_representations_of_one_instant_compare_equal() -> None:
    instant = datetime(2026, 4, 18, 0, 0, tzinfo=UTC)
    assert normalise_as_of(instant) == instant
    assert normalise_as_of(datetime(2026, 4, 18)) == instant
    assert normalise_as_of(date(2026, 4, 18)) == instant
    assert normalise_as_of("2026-04-18") == instant
    assert normalise_as_of(datetime(2026, 4, 18, 5, tzinfo=timezone(timedelta(hours=5)))) == instant


def test_non_iso_string_raises() -> None:
    with pytest.raises(ValueError):
        normalise_as_of("18/04/2026")
