"""Data quality validation wrappers for ingestion boundaries.

Provides batch Pydantic validation with structured rejection logging (DQ-01)
and score range enforcement (DQ-03). All ingestion data should pass through
validate_records() before entering the processing pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RejectedRecord:
    """Structured error details for a record that failed validation.

    Args:
        raw_data: The original dict that failed validation.
        error_count: Number of validation errors found.
        error_details: Human-readable string of all validation errors.
    """

    raw_data: dict
    error_count: int
    error_details: str


@dataclass(frozen=True)
class ValidationResult:
    """Immutable result of batch record validation.

    Args:
        valid: List of successfully validated Pydantic model instances.
        rejected: List of RejectedRecord entries for failed records.
        model_name: Name of the Pydantic model used for validation.
    """

    valid: list = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)
    model_name: str = ""

    @property
    def total(self) -> int:
        """Total number of records attempted (valid + rejected)."""
        return len(self.valid) + len(self.rejected)

    @property
    def rejection_rate(self) -> float:
        """Fraction of records rejected (0.0 to 1.0)."""
        if self.total == 0:
            return 0.0
        return len(self.rejected) / self.total


def validate_records(raw_records: list[dict], model: type[BaseModel]) -> ValidationResult:
    """Validate a batch of raw dicts against a Pydantic model.

    Each dict is validated independently. Valid records are returned as model
    instances; invalid records are captured as RejectedRecord entries with
    structured error details and logged as structlog warnings.

    Args:
        raw_records: List of raw dicts to validate.
        model: Pydantic model class to validate against.

    Returns:
        ValidationResult with valid and rejected records.
    """
    from pydantic import ValidationError

    valid: list[BaseModel] = []
    rejected: list[RejectedRecord] = []

    for record in raw_records:
        try:
            validated = model.model_validate(record)
            valid.append(validated)
        except ValidationError as exc:
            details = str(exc)
            error_count = exc.error_count()
            rejected_entry = RejectedRecord(
                raw_data=record,
                error_count=error_count,
                error_details=details,
            )
            rejected.append(rejected_entry)
            logger.warning(
                "record_rejected",
                model=model.__name__,
                error_count=error_count,
                details=details,
            )

    return ValidationResult(
        valid=valid,
        rejected=rejected,
        model_name=model.__name__,
    )


def validate_score_range(score: int | float, field_name: str = "score") -> int:
    """Validate that a score is within the 0-100 range.

    Args:
        score: Score value to validate.
        field_name: Name of the field for error messages.

    Returns:
        Integer score value.

    Raises:
        ValueError: If score is outside 0-100 range.
    """
    if score < 0 or score > 100:
        msg = f"{field_name} must be between 0 and 100, got {score}"
        raise ValueError(msg)
    return int(score)
