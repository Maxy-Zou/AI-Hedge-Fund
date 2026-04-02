"""Type contracts for the pipeline orchestration layer.

Defines immutable result types used to track stage and pipeline execution outcomes.
All types are frozen dataclasses for immutability per project conventions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class StageResult:
    """Immutable result of a single pipeline stage execution.

    Args:
        stage: Name of the pipeline stage (e.g. "sec_filings", "patents").
        status: Outcome status (e.g. "success", "partial", "failed").
        companies_processed: Number of companies processed in this stage.
        errors: List of error messages encountered during execution.
    """

    stage: str
    status: str
    companies_processed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PipelineRunResult:
    """Immutable result of a full pipeline run across all stages.

    Args:
        run_id: Unique identifier for this pipeline run.
        started_at: UTC timestamp when the run started.
        ended_at: UTC timestamp when the run ended.
        status: Overall outcome status.
        stages: List of individual stage results.
        companies_processed: Total companies processed across all stages.
        total_errors: Computed sum of errors across all stages.
    """

    run_id: uuid.UUID
    started_at: datetime
    ended_at: datetime
    status: str
    stages: list[StageResult]
    companies_processed: int
    total_errors: int = 0

    def __post_init__(self) -> None:
        """Compute total_errors from stages if not explicitly provided."""
        computed = sum(len(s.errors) for s in self.stages)
        object.__setattr__(self, "total_errors", computed)
