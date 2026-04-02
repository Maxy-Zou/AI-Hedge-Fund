"""Prefect-compatible stage wrappers for pipeline execution.

Each stage function wraps an existing collector or scorer, returning an
immutable StageResult with status, companies processed, and error details.
Stages are plain functions (not @task) since collectors already handle retries
via tenacity. The daily_flow.py module orchestrates them as a @flow.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog

from ai_washer.pipeline.types import StageResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ai_washer.config import AppSettings

logger = structlog.get_logger(__name__)


def collect_sec_filings_stage(settings: AppSettings) -> StageResult:
    """Wrap FilingCollector.collect_all() as a pipeline stage.

    Args:
        settings: Application settings for constructing the collector.

    Returns:
        StageResult with stage="sec_filings".
    """
    from ai_washer.ingestion.filing_collector import FilingCollector

    try:
        logger.info("stage_started", stage="sec_filings")
        collector = FilingCollector(app_settings=settings)
        results = collector.collect_all()
        errors = [e for r in results for e in r.errors]
        status = "succeeded" if not errors else "partially_failed"
        stage_result = StageResult(
            stage="sec_filings",
            status=status,
            companies_processed=len(results),
            errors=errors,
        )
        logger.info("stage_completed", stage="sec_filings", status=status)
        return stage_result
    except Exception as exc:
        logger.warning("stage_failed", stage="sec_filings", error=str(exc), exc_info=True)
        return StageResult(stage="sec_filings", status="failed", errors=[str(exc)])


def collect_patents_stage(settings: AppSettings) -> StageResult:
    """Wrap PatentCollector.collect_all() as a pipeline stage.

    Args:
        settings: Application settings for constructing the collector.

    Returns:
        StageResult with stage="patents".
    """
    from ai_washer.ingestion.patent_collector import PatentCollector

    try:
        logger.info("stage_started", stage="patents")
        collector = PatentCollector(app_settings=settings)
        results = collector.collect_all()
        errors = [e for r in results for e in r.errors]
        status = "succeeded" if not errors else "partially_failed"
        stage_result = StageResult(
            stage="patents",
            status=status,
            companies_processed=len(results),
            errors=errors,
        )
        logger.info("stage_completed", stage="patents", status=status)
        return stage_result
    except Exception as exc:
        logger.warning("stage_failed", stage="patents", error=str(exc), exc_info=True)
        return StageResult(stage="patents", status="failed", errors=[str(exc)])


def collect_github_stage(settings: AppSettings) -> StageResult:
    """Wrap GitHubCollector.collect_all() as a pipeline stage.

    Args:
        settings: Application settings for constructing the collector.

    Returns:
        StageResult with stage="github".
    """
    from ai_washer.ingestion.github_collector import GitHubCollector

    try:
        logger.info("stage_started", stage="github")
        collector = GitHubCollector(app_settings=settings)
        results = collector.collect_all()
        errors = [e for r in results for e in r.errors]
        status = "succeeded" if not errors else "partially_failed"
        stage_result = StageResult(
            stage="github",
            status=status,
            companies_processed=len(results),
            errors=errors,
        )
        logger.info("stage_completed", stage="github", status=status)
        return stage_result
    except Exception as exc:
        logger.warning("stage_failed", stage="github", error=str(exc), exc_info=True)
        return StageResult(stage="github", status="failed", errors=[str(exc)])


def collect_earnings_stage(settings: AppSettings) -> StageResult:
    """Wrap EarningsCollector.collect_all() as a pipeline stage.

    Args:
        settings: Application settings for constructing the collector.

    Returns:
        StageResult with stage="earnings".
    """
    from ai_washer.ingestion.earnings_collector import EarningsCollector

    try:
        logger.info("stage_started", stage="earnings")
        collector = EarningsCollector(app_settings=settings)
        results = collector.collect_all()
        errors = [e for r in results for e in r.errors]
        status = "succeeded" if not errors else "partially_failed"
        stage_result = StageResult(
            stage="earnings",
            status=status,
            companies_processed=len(results),
            errors=errors,
        )
        logger.info("stage_completed", stage="earnings", status=status)
        return stage_result
    except Exception as exc:
        logger.warning("stage_failed", stage="earnings", error=str(exc), exc_info=True)
        return StageResult(stage="earnings", status="failed", errors=[str(exc)])


def collect_jobs_stage(settings: AppSettings) -> StageResult:
    """Wrap JobCollector.collect_all() as a pipeline stage.

    Args:
        settings: Application settings for constructing the collector.

    Returns:
        StageResult with stage="jobs".
    """
    from ai_washer.ingestion.job_collector import JobCollector

    try:
        logger.info("stage_started", stage="jobs")
        collector = JobCollector(app_settings=settings)
        results = collector.collect_all()
        errors = [e for r in results for e in r.errors]
        status = "succeeded" if not errors else "partially_failed"
        stage_result = StageResult(
            stage="jobs",
            status=status,
            companies_processed=len(results),
            errors=errors,
        )
        logger.info("stage_completed", stage="jobs", status=status)
        return stage_result
    except Exception as exc:
        logger.warning("stage_failed", stage="jobs", error=str(exc), exc_info=True)
        return StageResult(stage="jobs", status="failed", errors=[str(exc)])


def score_all_stage(session: Session, run_id: uuid.UUID) -> StageResult:
    """Wrap ScoringOrchestrator.score_all() as a pipeline stage.

    Args:
        session: SQLAlchemy session for database operations.
        run_id: Pipeline run UUID for correlation.

    Returns:
        StageResult with stage="scoring".
    """
    from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator
    from ai_washer.config import load_scoring_config

    try:
        logger.info("stage_started", stage="scoring")
        scoring_config = load_scoring_config()
        orch = ScoringOrchestrator(
            session=session,
            config=scoring_config,
            run_id=run_id,
        )
        all_results = orch.score_all()
        companies_count = len(all_results)
        errors: list[str] = []
        stage_result = StageResult(
            stage="scoring",
            status="succeeded" if not errors else "partially_failed",
            companies_processed=companies_count,
            errors=errors,
        )
        logger.info("stage_completed", stage="scoring", status=stage_result.status)
        return stage_result
    except Exception as exc:
        logger.warning("stage_failed", stage="scoring", error=str(exc), exc_info=True)
        return StageResult(stage="scoring", status="failed", errors=[str(exc)])


def compute_composites_stage(session: Session, run_id: uuid.UUID) -> StageResult:
    """Wrap composite score computation as a pipeline stage.

    Calls ScoringOrchestrator.score_all() which already includes composite
    computation, but this stage is explicit for tracking purposes.

    Args:
        session: SQLAlchemy session for database operations.
        run_id: Pipeline run UUID for correlation.

    Returns:
        StageResult with stage="composites".
    """
    from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator
    from ai_washer.config import load_scoring_config

    try:
        logger.info("stage_started", stage="composites")
        scoring_config = load_scoring_config()
        orch = ScoringOrchestrator(
            session=session,
            config=scoring_config,
            run_id=run_id,
        )
        # score_all already handles composite computation internally
        all_results = orch.score_all()
        companies_count = len(all_results)
        stage_result = StageResult(
            stage="composites",
            status="succeeded",
            companies_processed=companies_count,
        )
        logger.info("stage_completed", stage="composites", status="succeeded")
        return stage_result
    except Exception as exc:
        logger.warning("stage_failed", stage="composites", error=str(exc), exc_info=True)
        return StageResult(stage="composites", status="failed", errors=[str(exc)])
