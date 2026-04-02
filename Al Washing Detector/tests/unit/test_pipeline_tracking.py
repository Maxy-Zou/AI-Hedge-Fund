"""Tests for pipeline run tracking persistence (OPS-04).

Verifies that PipelineRun rows are correctly persisted with status,
timestamps, companies_processed, and per-source error breakdown.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from ai_washer.db.models import PipelineRun
from ai_washer.pipeline.correlation import end_pipeline_run, start_pipeline_run
from ai_washer.pipeline.types import PipelineRunResult, StageResult


@pytest.fixture()
def sqlite_session():
    """Create an in-memory SQLite session with PipelineRun table only."""
    engine = create_engine("sqlite:///:memory:")

    # Create PipelineRun table using raw DDL (avoid JSONB issues)
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE pipeline_runs (
                    id TEXT PRIMARY KEY,
                    started_at TIMESTAMP NOT NULL,
                    ended_at TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'running',
                    companies_processed INTEGER NOT NULL DEFAULT 0,
                    errors TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.commit()

    # Map ORM to the raw table
    from sqlalchemy.orm import Session as OrmSession

    sm = sessionmaker(bind=engine, expire_on_commit=False)

    # Intercept PipelineRun inserts/updates to handle JSON as text
    @event.listens_for(sm, "before_flush")
    def _before_flush(session, flush_context, instances):
        import json

        for obj in session.new | session.dirty:
            if isinstance(obj, PipelineRun) and isinstance(obj.errors, list):
                object.__setattr__(obj, "_raw_errors", obj.errors)

    with sm() as session:
        yield session


class TestPipelineRunTracking:
    """Verify PipelineRun lifecycle: start -> stages -> end."""

    def test_start_pipeline_run_creates_row(self, sqlite_session: Session) -> None:
        run_id = start_pipeline_run(sqlite_session)

        row = sqlite_session.get(PipelineRun, run_id)
        assert row is not None
        assert row.status == "running"
        assert row.started_at is not None

    def test_end_pipeline_run_updates_row(self, sqlite_session: Session) -> None:
        run_id = start_pipeline_run(sqlite_session)

        stages = [
            StageResult(stage="sec_filings", status="succeeded", companies_processed=10),
            StageResult(stage="patents", status="failed", errors=["API timeout"]),
        ]

        result = end_pipeline_run(sqlite_session, run_id, stages)

        assert result.status == "partially_failed"
        assert result.companies_processed == 10
        assert result.total_errors == 1

        row = sqlite_session.get(PipelineRun, run_id)
        assert row is not None
        assert row.ended_at is not None
        assert row.status == "partially_failed"

    def test_end_pipeline_run_all_succeeded(self, sqlite_session: Session) -> None:
        run_id = start_pipeline_run(sqlite_session)

        stages = [
            StageResult(stage="sec_filings", status="succeeded", companies_processed=5),
            StageResult(stage="scoring", status="succeeded", companies_processed=5),
        ]

        result = end_pipeline_run(sqlite_session, run_id, stages)

        assert result.status == "succeeded"
        assert result.total_errors == 0

    def test_end_pipeline_run_all_failed(self, sqlite_session: Session) -> None:
        run_id = start_pipeline_run(sqlite_session)

        stages = [
            StageResult(stage="sec_filings", status="failed", errors=["down"]),
            StageResult(stage="patents", status="failed", errors=["down"]),
        ]

        result = end_pipeline_run(sqlite_session, run_id, stages)

        assert result.status == "failed"
        assert result.total_errors == 2

    def test_pipeline_run_result_has_all_fields(self, sqlite_session: Session) -> None:
        run_id = start_pipeline_run(sqlite_session)

        stages = [
            StageResult(stage="sec_filings", status="succeeded", companies_processed=10),
        ]

        result = end_pipeline_run(sqlite_session, run_id, stages)

        assert isinstance(result, PipelineRunResult)
        assert result.run_id == run_id
        assert result.started_at is not None
        assert result.ended_at is not None
        assert len(result.stages) == 1
