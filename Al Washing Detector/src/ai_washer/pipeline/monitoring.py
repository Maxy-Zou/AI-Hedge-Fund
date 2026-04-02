"""Data source staleness monitoring for the pipeline.

Detects stale data sources (DQ-02) by comparing last_success timestamps
against expected refresh cadences. Provides functions to update source
status after collection runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_washer.db.models import DataSourceStatus

logger = structlog.get_logger(__name__)

_DEFAULT_CADENCE_HOURS = 24


@dataclass(frozen=True)
class StalenessReport:
    """Immutable report for a single stale data source.

    Args:
        source_name: Name of the data source (e.g. "sec_filings").
        reason: Why it is stale ("exceeded_cadence" or "never_succeeded").
        hours_since: Hours since last success (None if never succeeded).
        expected_hours: Expected refresh cadence in hours.
    """

    source_name: str
    reason: str
    hours_since: float | None
    expected_hours: int


def check_staleness(
    session: Session,
    *,
    now_utc: datetime | None = None,
) -> list[StalenessReport]:
    """Check all data sources for staleness.

    Queries DataSourceStatus rows, compares last_success_at against
    expected_cadence_hours, and returns reports for stale sources.
    Also updates the is_stale column on each row as a side effect.

    Args:
        session: SQLAlchemy session (caller manages transaction).
        now_utc: Override for current UTC time (for testing). Defaults to now.

    Returns:
        List of StalenessReport for sources that are stale or have never succeeded.
    """
    if now_utc is None:
        now_utc = datetime.now(tz=UTC)
    stmt = select(DataSourceStatus)
    rows = list(session.execute(stmt).scalars().all())

    stale_reports: list[StalenessReport] = []

    for row in rows:
        if row.last_success_at is None:
            report = StalenessReport(
                source_name=row.source_name,
                reason="never_succeeded",
                hours_since=None,
                expected_hours=row.expected_cadence_hours,
            )
            stale_reports.append(report)
            row.is_stale = True
            logger.warning(
                "source_stale",
                source_name=row.source_name,
                reason="never_succeeded",
            )
            continue

        # Handle timezone-naive datetimes (e.g. from SQLite in tests)
        last_success = row.last_success_at
        if last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=UTC)

        hours_since = (now_utc - last_success).total_seconds() / 3600.0

        if hours_since > row.expected_cadence_hours:
            report = StalenessReport(
                source_name=row.source_name,
                reason="exceeded_cadence",
                hours_since=hours_since,
                expected_hours=row.expected_cadence_hours,
            )
            stale_reports.append(report)
            row.is_stale = True
            logger.warning(
                "source_stale",
                source_name=row.source_name,
                reason="exceeded_cadence",
                hours_since=round(hours_since, 1),
                expected_hours=row.expected_cadence_hours,
            )
        else:
            row.is_stale = False

    session.flush()
    return stale_reports


def update_source_status(
    session: Session,
    source_name: str,
    *,
    success: bool,
    error_message: str | None = None,
    now_utc: datetime | None = None,
) -> None:
    """Record success or failure for a data source.

    Finds the DataSourceStatus row by source_name (creates if missing).
    On success: sets last_success_at and clears is_stale.
    On failure: sets last_error_at, last_error_message, and marks is_stale.

    Args:
        session: SQLAlchemy session (caller manages transaction).
        source_name: Name of the data source.
        success: Whether the collection succeeded.
        error_message: Error details (used when success=False).
        now_utc: Override for current UTC time (for testing). Defaults to now.
    """
    import uuid

    if now_utc is None:
        now_utc = datetime.now(tz=UTC)

    stmt = select(DataSourceStatus).where(DataSourceStatus.source_name == source_name)
    row = session.execute(stmt).scalar_one_or_none()

    if row is None:
        row = DataSourceStatus(
            id=uuid.uuid4(),
            source_name=source_name,
            expected_cadence_hours=_DEFAULT_CADENCE_HOURS,
            updated_at=now_utc,
        )
        session.add(row)

    if success:
        row.last_success_at = now_utc
        row.is_stale = False
        logger.info("source_status_updated", source_name=source_name, success=True)
    else:
        row.last_error_at = now_utc
        row.last_error_message = error_message
        row.is_stale = True
        logger.warning(
            "source_status_updated",
            source_name=source_name,
            success=False,
            error_message=error_message,
        )

    row.updated_at = now_utc
    session.flush()


def get_all_source_status(session: Session) -> list[DataSourceStatus]:
    """Return all DataSourceStatus records ordered by source_name.

    Args:
        session: SQLAlchemy session.

    Returns:
        List of DataSourceStatus rows ordered alphabetically.
    """
    stmt = select(DataSourceStatus).order_by(DataSourceStatus.source_name)
    return list(session.execute(stmt).scalars().all())
