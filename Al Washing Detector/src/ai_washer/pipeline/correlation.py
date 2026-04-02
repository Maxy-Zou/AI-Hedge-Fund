"""Pipeline correlation ID helpers and PipelineRun lifecycle management.

Provides start/end helpers that bind a unique run_id to structlog contextvars
so every log line within a pipeline run is traceable. Also manages PipelineRun
database records for status tracking and stale run detection.

Usage::

    run_id = start_pipeline_run(session)
    # ... execute pipeline stages ...
    result = end_pipeline_run(session, run_id, stages)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session

from ai_washer.db.models import PipelineRun
from ai_washer.pipeline.types import PipelineRunResult, StageResult

logger = structlog.get_logger(__name__)


def start_pipeline_run(session: Session) -> uuid.UUID:
    """Start a new pipeline run: create DB record and bind correlation ID.

    Args:
        session: SQLAlchemy session for persisting the PipelineRun row.

    Returns:
        The generated run_id UUID.
    """
    run_id = uuid.uuid4()
    now = datetime.now(UTC)

    # Clear any leaked contextvars from a prior run
    structlog.contextvars.clear_contextvars()

    # Bind correlation ID for all subsequent log lines
    structlog.contextvars.bind_contextvars(
        run_id=str(run_id),
        pipeline="daily_batch",
    )

    # Persist PipelineRun record
    pipeline_run = PipelineRun(
        id=run_id,
        started_at=now,
        status="running",
        companies_processed=0,
        errors=[],
    )
    session.add(pipeline_run)
    session.flush()

    logger.info("pipeline_run_started", run_id=str(run_id))
    return run_id


def end_pipeline_run(
    session: Session,
    run_id: uuid.UUID,
    stages: list[StageResult],
) -> PipelineRunResult:
    """Finalize a pipeline run: update DB record and clear correlation ID.

    Computes overall status from stage results, builds per-source error
    breakdown, and updates the PipelineRun row.

    Args:
        session: SQLAlchemy session for updating the PipelineRun row.
        run_id: The pipeline run UUID from start_pipeline_run.
        stages: List of StageResult from each pipeline stage.

    Returns:
        Immutable PipelineRunResult with full run details.
    """
    now = datetime.now(UTC)

    # Compute overall status
    status = _compute_status(stages)

    # Compute companies_processed as max across stages (same companies
    # flow through multiple stages)
    companies_processed = max(
        (s.companies_processed for s in stages),
        default=0,
    )

    # Build per-source error JSONB
    errors_jsonb: list[dict[str, object]] = [
        {"stage": s.stage, "errors": s.errors} for s in stages if s.errors
    ]

    total_errors = sum(len(s.errors) for s in stages)

    # Update PipelineRun record
    pipeline_run = session.get(PipelineRun, run_id)
    if pipeline_run is not None:
        pipeline_run.ended_at = now
        pipeline_run.status = status
        pipeline_run.companies_processed = companies_processed
        pipeline_run.errors = errors_jsonb
        session.flush()

    logger.info(
        "pipeline_run_ended",
        run_id=str(run_id),
        status=status,
        total_errors=total_errors,
    )

    # Clear contextvars to prevent leaking into unrelated code
    structlog.contextvars.clear_contextvars()

    # Look up started_at from the DB record for the result
    started_at = pipeline_run.started_at if pipeline_run else now

    return PipelineRunResult(
        run_id=run_id,
        started_at=started_at,
        ended_at=now,
        status=status,
        stages=stages,
        companies_processed=companies_processed,
        total_errors=total_errors,
    )


def mark_stale_runs(session: Session, threshold_hours: int = 4) -> int:
    """Mark stale pipeline runs as crashed.

    Any PipelineRun with status='running' that started more than
    threshold_hours ago is assumed to have crashed without cleanup.

    Args:
        session: SQLAlchemy session for querying and updating.
        threshold_hours: Hours after which a running pipeline is considered stale.

    Returns:
        Number of runs marked as crashed.
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=threshold_hours)

    stale_runs = (
        session.query(PipelineRun)
        .filter(
            PipelineRun.status == "running",
            PipelineRun.started_at < cutoff,
        )
        .all()
    )

    for run in stale_runs:
        run.status = "crashed"
        run.ended_at = now

    count = len(stale_runs)
    if count > 0:
        logger.warning("stale_runs_marked", count=count, threshold_hours=threshold_hours)

    return count


def _compute_status(stages: list[StageResult]) -> str:
    """Compute overall pipeline status from stage results.

    Returns:
        "succeeded" if all stages succeeded,
        "failed" if all stages failed,
        "partially_failed" if mixed results.
    """
    if not stages:
        return "succeeded"

    all_succeeded = all(s.status == "succeeded" for s in stages)
    all_failed = all(s.status == "failed" for s in stages)

    if all_succeeded:
        return "succeeded"
    if all_failed:
        return "failed"
    return "partially_failed"
