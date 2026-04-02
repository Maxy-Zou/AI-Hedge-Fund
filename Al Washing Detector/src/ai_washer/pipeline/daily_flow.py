"""Prefect-orchestrated daily pipeline flow.

Runs all ingestion stages sequentially (SEC compliance rate limits),
then scoring, with per-stage error isolation. Each stage failure is
captured but does not prevent subsequent stages from running.

Usage::

    from ai_washer.pipeline.daily_flow import daily_pipeline_flow
    result = daily_pipeline_flow()
"""

from __future__ import annotations

import structlog
from prefect import flow

from ai_washer.config import load_app_settings
from ai_washer.db.session import create_engine_from_settings, get_session_factory
from ai_washer.pipeline.correlation import end_pipeline_run, mark_stale_runs, start_pipeline_run
from ai_washer.pipeline.monitoring import update_source_status
from ai_washer.pipeline.stages import (
    collect_earnings_stage,
    collect_github_stage,
    collect_jobs_stage,
    collect_patents_stage,
    collect_sec_filings_stage,
    compute_composites_stage,
    score_all_stage,
)
from ai_washer.pipeline.types import PipelineRunResult, StageResult

logger = structlog.get_logger(__name__)


@flow(name="daily-ai-washing-pipeline", log_prints=True)
def daily_pipeline_flow() -> PipelineRunResult:
    """Execute the full daily AI washing detection pipeline.

    Orchestrates ingestion (5 data sources), scoring, and composite
    computation. Each stage runs independently -- a failure in one
    source does not prevent other sources or scoring from running.

    Returns:
        PipelineRunResult with overall status and per-stage breakdown.
    """
    settings = load_app_settings()
    engine = create_engine_from_settings(settings)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        # Clean up any crashed runs from prior executions
        mark_stale_runs(session)
        session.commit()

        # Start a new pipeline run (creates DB record + binds correlation ID)
        run_id = start_pipeline_run(session)
        session.commit()

        stages: list[StageResult] = []

        try:
            # -- Ingestion stages (sequential for SEC rate compliance) --

            sec_result = collect_sec_filings_stage(settings)
            stages.append(sec_result)
            update_source_status(
                session,
                "sec_filings",
                success=sec_result.status != "failed",
                error_message="; ".join(sec_result.errors) if sec_result.errors else None,
            )

            patent_result = collect_patents_stage(settings)
            stages.append(patent_result)
            update_source_status(
                session,
                "patents",
                success=patent_result.status != "failed",
                error_message="; ".join(patent_result.errors) if patent_result.errors else None,
            )

            github_result = collect_github_stage(settings)
            stages.append(github_result)
            update_source_status(
                session,
                "github",
                success=github_result.status != "failed",
                error_message="; ".join(github_result.errors) if github_result.errors else None,
            )

            earnings_result = collect_earnings_stage(settings)
            stages.append(earnings_result)
            update_source_status(
                session,
                "earnings",
                success=earnings_result.status != "failed",
                error_message=(
                    "; ".join(earnings_result.errors) if earnings_result.errors else None
                ),
            )

            jobs_result = collect_jobs_stage(settings)
            stages.append(jobs_result)
            update_source_status(
                session,
                "jobs",
                success=jobs_result.status != "failed",
                error_message="; ".join(jobs_result.errors) if jobs_result.errors else None,
            )

            session.commit()

            # -- Scoring stages --

            score_result = score_all_stage(session, run_id)
            stages.append(score_result)

            composite_result = compute_composites_stage(session, run_id)
            stages.append(composite_result)

            session.commit()

        finally:
            # Always finalize the pipeline run, even on unexpected errors
            result = end_pipeline_run(session, run_id, stages)
            session.commit()

    logger.info(
        "daily_pipeline_complete",
        status=result.status,
        companies_processed=result.companies_processed,
        total_errors=result.total_errors,
    )

    return result
