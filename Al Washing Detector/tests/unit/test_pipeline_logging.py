"""Tests for pipeline correlation ID helpers and PipelineRun lifecycle.

Covers OPS-02 (correlation IDs in structlog) and OPS-04 (pipeline run tracking).
Uses SQLite in-memory database for isolation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_washer.db.base import Base
from ai_washer.db.models import PipelineRun
from ai_washer.pipeline.correlation import (
    end_pipeline_run,
    mark_stale_runs,
    start_pipeline_run,
)
from ai_washer.pipeline.types import StageResult


def _make_session() -> Session:
    """Create an in-memory SQLite session with PipelineRun table.

    Patches JSONB columns to JSON since SQLite lacks JSONB support.
    Per project convention (SQLite JSONB-to-JSON type adapter pattern).
    """
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    engine = create_engine("sqlite:///:memory:")

    # Patch JSONB columns to use JSON for SQLite compatibility
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


class TestStartPipelineRun:
    """Tests for start_pipeline_run."""

    def test_returns_uuid_run_id(self) -> None:
        """start_pipeline_run returns a UUID run_id."""
        session = _make_session()
        run_id = start_pipeline_run(session)
        assert isinstance(run_id, uuid.UUID)

    def test_creates_pipeline_run_row_with_running_status(self) -> None:
        """start_pipeline_run creates a PipelineRun row with status='running'."""
        session = _make_session()
        run_id = start_pipeline_run(session)
        session.commit()

        row = session.get(PipelineRun, run_id)
        assert row is not None
        assert row.status == "running"
        assert row.id == run_id

    def test_binds_run_id_and_pipeline_to_contextvars(self) -> None:
        """start_pipeline_run binds run_id and pipeline to structlog contextvars."""
        session = _make_session()
        run_id = start_pipeline_run(session)

        ctx = structlog.contextvars.get_contextvars()
        assert ctx["run_id"] == str(run_id)
        assert ctx["pipeline"] == "daily_batch"

        # Clean up
        structlog.contextvars.clear_contextvars()


class TestEndPipelineRun:
    """Tests for end_pipeline_run."""

    def _start_run(self, session: Session) -> uuid.UUID:
        """Helper: start a pipeline run and commit."""
        run_id = start_pipeline_run(session)
        session.commit()
        structlog.contextvars.clear_contextvars()
        return run_id

    def test_updates_pipeline_run_with_ended_at_and_status(self) -> None:
        """end_pipeline_run sets ended_at, status, companies_processed, errors."""
        session = _make_session()
        run_id = self._start_run(session)

        stages = [
            StageResult(stage="sec_filings", status="succeeded", companies_processed=10),
        ]
        result = end_pipeline_run(session, run_id, stages)
        session.commit()

        row = session.get(PipelineRun, run_id)
        assert row is not None
        assert row.ended_at is not None
        assert row.status == "succeeded"
        assert row.companies_processed == 10
        assert result.run_id == run_id

    def test_clears_contextvars(self) -> None:
        """end_pipeline_run clears structlog contextvars."""
        session = _make_session()
        run_id = self._start_run(session)

        # Bind some vars to verify they get cleared
        structlog.contextvars.bind_contextvars(run_id=str(run_id), pipeline="daily_batch")

        stages = [StageResult(stage="test", status="succeeded")]
        end_pipeline_run(session, run_id, stages)

        ctx = structlog.contextvars.get_contextvars()
        assert "run_id" not in ctx
        assert "pipeline" not in ctx

    def test_status_succeeded_when_all_stages_succeeded(self) -> None:
        """end_pipeline_run sets status='succeeded' when all stages succeeded."""
        session = _make_session()
        run_id = self._start_run(session)

        stages = [
            StageResult(stage="sec_filings", status="succeeded", companies_processed=5),
            StageResult(stage="patents", status="succeeded", companies_processed=5),
            StageResult(stage="github", status="succeeded", companies_processed=5),
        ]
        result = end_pipeline_run(session, run_id, stages)
        assert result.status == "succeeded"

    def test_status_partially_failed_when_some_stages_failed(self) -> None:
        """end_pipeline_run sets status='partially_failed' when mixed results."""
        session = _make_session()
        run_id = self._start_run(session)

        stages = [
            StageResult(stage="sec_filings", status="succeeded", companies_processed=5),
            StageResult(stage="patents", status="failed", errors=["timeout"]),
        ]
        result = end_pipeline_run(session, run_id, stages)
        assert result.status == "partially_failed"

    def test_status_failed_when_all_stages_failed(self) -> None:
        """end_pipeline_run sets status='failed' when all stages failed."""
        session = _make_session()
        run_id = self._start_run(session)

        stages = [
            StageResult(stage="sec_filings", status="failed", errors=["timeout"]),
            StageResult(stage="patents", status="failed", errors=["rate_limited"]),
        ]
        result = end_pipeline_run(session, run_id, stages)
        assert result.status == "failed"

    def test_stores_per_source_errors_in_jsonb(self) -> None:
        """end_pipeline_run stores per-source errors in JSONB format."""
        session = _make_session()
        run_id = self._start_run(session)

        stages = [
            StageResult(stage="patents", status="failed", errors=["timeout", "parse_error"]),
            StageResult(stage="github", status="succeeded"),
        ]
        result = end_pipeline_run(session, run_id, stages)
        session.commit()

        row = session.get(PipelineRun, run_id)
        assert row is not None
        # Errors should be list of dicts with stage and errors
        assert len(row.errors) == 1
        assert row.errors[0]["stage"] == "patents"
        assert row.errors[0]["errors"] == ["timeout", "parse_error"]

        # Result total_errors should be 2
        assert result.total_errors == 2


class TestMarkStaleRuns:
    """Tests for mark_stale_runs."""

    def test_marks_old_running_pipelines_as_crashed(self) -> None:
        """mark_stale_runs sets status='crashed' on stale running pipelines."""
        session = _make_session()

        # Create a stale run (started 5 hours ago, still "running")
        stale_run = PipelineRun(
            id=uuid.uuid4(),
            started_at=datetime.now(timezone.utc) - timedelta(hours=5),
            status="running",
            companies_processed=0,
            errors=[],
        )
        session.add(stale_run)
        session.commit()

        count = mark_stale_runs(session, threshold_hours=4)
        session.commit()

        assert count == 1
        session.refresh(stale_run)
        assert stale_run.status == "crashed"
        assert stale_run.ended_at is not None

    def test_does_not_mark_recent_running_pipelines(self) -> None:
        """mark_stale_runs ignores recently started running pipelines."""
        session = _make_session()

        # Create a recent run (started 1 hour ago, still "running")
        recent_run = PipelineRun(
            id=uuid.uuid4(),
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            status="running",
            companies_processed=0,
            errors=[],
        )
        session.add(recent_run)
        session.commit()

        count = mark_stale_runs(session, threshold_hours=4)
        assert count == 0

        session.refresh(recent_run)
        assert recent_run.status == "running"

    def test_does_not_mark_completed_pipelines(self) -> None:
        """mark_stale_runs ignores pipelines that already completed."""
        session = _make_session()

        completed_run = PipelineRun(
            id=uuid.uuid4(),
            started_at=datetime.now(timezone.utc) - timedelta(hours=10),
            ended_at=datetime.now(timezone.utc) - timedelta(hours=9),
            status="succeeded",
            companies_processed=5,
            errors=[],
        )
        session.add(completed_run)
        session.commit()

        count = mark_stale_runs(session, threshold_hours=4)
        assert count == 0
