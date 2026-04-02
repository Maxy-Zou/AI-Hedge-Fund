"""Tests for pipeline data source staleness monitoring.

Covers DQ-02 (staleness detection when last_success exceeds expected cadence).
Uses SQLite in-memory DB with DataSourceStatus table.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_washer.db.models import DataSourceStatus
from ai_washer.pipeline.monitoring import (
    StalenessReport,
    check_staleness,
    get_all_source_status,
    update_source_status,
)

# Fixed reference time for deterministic tests
_NOW = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    """Create an in-memory SQLite session with DataSourceStatus table only.

    Creates only the data_source_status table (not the full schema) to avoid
    JSONB compatibility issues with SQLite on other models.
    """
    engine = create_engine("sqlite:///:memory:")
    DataSourceStatus.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    yield session
    session.close()


def _make_source(
    session: Session,
    name: str,
    *,
    cadence_hours: int = 24,
    last_success_at: datetime | None = None,
    last_error_at: datetime | None = None,
    last_error_message: str | None = None,
    is_stale: bool = False,
) -> DataSourceStatus:
    """Helper to insert a DataSourceStatus row."""
    row = DataSourceStatus(
        id=uuid.uuid4(),
        source_name=name,
        expected_cadence_hours=cadence_hours,
        last_success_at=last_success_at,
        last_error_at=last_error_at,
        last_error_message=last_error_message,
        is_stale=is_stale,
        updated_at=datetime.now(tz=timezone.utc),
    )
    session.add(row)
    session.flush()
    return row


# ---------------------------------------------------------------------------
# Test 4: StalenessReport shape
# ---------------------------------------------------------------------------


class TestStalenessReportShape:
    """StalenessReport is frozen with correct fields."""

    def test_frozen(self):
        report = StalenessReport(
            source_name="sec", reason="exceeded_cadence", hours_since=30.0, expected_hours=24
        )
        with pytest.raises(AttributeError):
            report.reason = "x"  # type: ignore[misc]

    def test_fields(self):
        report = StalenessReport(
            source_name="sec", reason="never_succeeded", hours_since=None, expected_hours=24
        )
        assert report.source_name == "sec"
        assert report.reason == "never_succeeded"
        assert report.hours_since is None
        assert report.expected_hours == 24


# ---------------------------------------------------------------------------
# Tests 1-3: check_staleness
# ---------------------------------------------------------------------------


class TestCheckStaleness:
    """check_staleness detects stale and never-succeeded sources."""

    def test_fresh_sources_return_empty(self, db_session):
        """Test 1: all sources within cadence -> empty list."""
        # 12 hours ago, cadence is 24h -> fresh
        _make_source(
            db_session,
            "sec_filings",
            cadence_hours=24,
            last_success_at=_NOW - timedelta(hours=12),
        )
        result = check_staleness(db_session, now_utc=_NOW)
        assert result == []

    def test_stale_source_flagged(self, db_session):
        """Test 2: hours since last_success exceeds cadence -> flagged."""
        # 36 hours ago, cadence is 24h -> stale
        _make_source(
            db_session,
            "patents",
            cadence_hours=24,
            last_success_at=_NOW - timedelta(hours=36),
        )
        result = check_staleness(db_session, now_utc=_NOW)
        assert len(result) == 1
        assert result[0].source_name == "patents"
        assert result[0].reason == "exceeded_cadence"
        assert result[0].hours_since is not None
        assert result[0].hours_since > 24.0
        assert result[0].expected_hours == 24

    def test_never_succeeded_flagged(self, db_session):
        """Test 3: last_success_at is None -> flagged as never_succeeded."""
        _make_source(db_session, "github", cadence_hours=24, last_success_at=None)
        result = check_staleness(db_session, now_utc=_NOW)
        assert len(result) == 1
        assert result[0].source_name == "github"
        assert result[0].reason == "never_succeeded"
        assert result[0].hours_since is None

    def test_updates_is_stale_column(self, db_session):
        """check_staleness updates the is_stale column on the DB row."""
        _make_source(
            db_session,
            "patents",
            cadence_hours=24,
            last_success_at=_NOW - timedelta(hours=36),
            is_stale=False,
        )
        check_staleness(db_session, now_utc=_NOW)
        row = db_session.query(DataSourceStatus).filter_by(source_name="patents").one()
        assert row.is_stale is True

    def test_fresh_source_cleared_stale(self, db_session):
        """check_staleness sets is_stale=False on fresh sources."""
        _make_source(
            db_session,
            "sec_filings",
            cadence_hours=24,
            last_success_at=_NOW - timedelta(hours=6),
            is_stale=True,
        )
        check_staleness(db_session, now_utc=_NOW)
        row = db_session.query(DataSourceStatus).filter_by(source_name="sec_filings").one()
        assert row.is_stale is False


# ---------------------------------------------------------------------------
# Tests 5-6: update_source_status
# ---------------------------------------------------------------------------


class TestUpdateSourceStatus:
    """update_source_status records success/failure timestamps."""

    def test_success_clears_stale(self, db_session):
        """Test 5: success=True sets last_success_at and is_stale=False."""
        _make_source(db_session, "sec_filings", cadence_hours=24, is_stale=True)
        update_source_status(db_session, "sec_filings", success=True, now_utc=_NOW)
        row = db_session.query(DataSourceStatus).filter_by(source_name="sec_filings").one()
        assert row.last_success_at is not None
        assert row.is_stale is False

    def test_failure_sets_error(self, db_session):
        """Test 6: success=False sets last_error_at, message, and is_stale=True."""
        _make_source(db_session, "github", cadence_hours=24)
        update_source_status(
            db_session, "github", success=False, error_message="rate limited", now_utc=_NOW
        )
        row = db_session.query(DataSourceStatus).filter_by(source_name="github").one()
        assert row.last_error_at is not None
        assert row.last_error_message == "rate limited"
        assert row.is_stale is True

    def test_creates_missing_source(self, db_session):
        """update_source_status creates a new row if source_name not found."""
        update_source_status(db_session, "new_source", success=True, now_utc=_NOW)
        row = db_session.query(DataSourceStatus).filter_by(source_name="new_source").one()
        assert row.last_success_at is not None
        assert row.is_stale is False
        # New source gets default cadence
        assert row.expected_cadence_hours == 24


# ---------------------------------------------------------------------------
# Test 7: get_all_source_status
# ---------------------------------------------------------------------------


class TestGetAllSourceStatus:
    """get_all_source_status returns all rows ordered by source_name."""

    def test_returns_all_ordered(self, db_session):
        """Test 7: returns list of all DataSourceStatus records ordered."""
        _make_source(db_session, "github", cadence_hours=24)
        _make_source(db_session, "sec_filings", cadence_hours=24)
        _make_source(db_session, "patents", cadence_hours=168)
        result = get_all_source_status(db_session)
        assert len(result) == 3
        names = [r.source_name for r in result]
        assert names == ["github", "patents", "sec_filings"]

    def test_returns_empty_when_no_sources(self, db_session):
        """Returns empty list when no sources exist."""
        result = get_all_source_status(db_session)
        assert result == []
