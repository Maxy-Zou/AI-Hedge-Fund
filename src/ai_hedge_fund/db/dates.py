"""Temporal normalisation shared by every ``as_of_date`` comparison.

``normalise_as_of`` is the single chokepoint that turns a loosely-typed
business date (ISO string, ``date``, naive or aware ``datetime``) into an
aware UTC ``datetime``. Every ``as_of_date <= target`` filter in the
codebase -- episodic recall, portfolio snapshot, paper-trade recall --
must go through it so the comparison is stable across SQLite (which
stores naive text) and PostgreSQL (timestamptz).

Promoted in Phase 9 from two byte-identical private copies
(``memory/episodic.py`` and ``risk/portfolio.py``); those modules now
re-export it under their previous private name for backwards compatibility.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def normalise_as_of(value: str | date | datetime) -> datetime:
    """Convert loose date/datetime/string inputs to an aware UTC datetime.

    Naive datetimes are treated as UTC. Plain dates become midnight UTC.
    Strings are parsed via :func:`datetime.fromisoformat` (ISO-8601 only);
    an explicit offset in the string is preserved.

    Raises:
        ValueError: The string is not ISO-8601.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


# US equity "trading day" is the America/New_York calendar date (Phase 11). A fill
# at 20:30 ET is still that day's fill even though it is the next day in UTC.
MARKET_TZ = ZoneInfo("America/New_York")


def trading_date(moment: datetime) -> date:
    """The New York calendar date of an aware ``moment``.

    Raises:
        ValueError: ``moment`` is naive -- its trading day would be a guess.
    """
    if moment.tzinfo is None:
        raise ValueError("trading_date needs a timezone-aware datetime")
    return moment.astimezone(MARKET_TZ).date()


def market_midnight_utc(day: date) -> datetime:
    """00:00 New York time on ``day``, as an aware UTC datetime (DST-correct)."""
    return datetime(day.year, day.month, day.day, tzinfo=MARKET_TZ).astimezone(UTC)
