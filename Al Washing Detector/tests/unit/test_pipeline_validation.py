"""Tests for pipeline data quality validation wrappers.

Covers DQ-01 (malformed record rejection with structured logs)
and DQ-03 (score range enforcement at boundaries).
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from ai_washer.pipeline.validation import (
    RejectedRecord,
    ValidationResult,
    validate_records,
    validate_score_range,
)


# ---------------------------------------------------------------------------
# Simple test model (avoids coupling to ingestion types)
# ---------------------------------------------------------------------------


class _SampleRecord(BaseModel):
    """Minimal model for testing validate_records."""

    name: str
    value: int


# ---------------------------------------------------------------------------
# Test 5: ValidationResult is frozen dataclass
# ---------------------------------------------------------------------------


class TestValidationResultShape:
    """ValidationResult and RejectedRecord have correct shape."""

    def test_validation_result_is_frozen(self):
        result = ValidationResult(valid=[], rejected=[], model_name="X")
        with pytest.raises(AttributeError):
            result.valid = []  # type: ignore[misc]

    def test_rejected_record_is_frozen(self):
        rec = RejectedRecord(raw_data={}, error_count=1, error_details="bad")
        with pytest.raises(AttributeError):
            rec.error_count = 2  # type: ignore[misc]

    def test_total_property(self):
        result = ValidationResult(
            valid=[_SampleRecord(name="a", value=1)],
            rejected=[RejectedRecord(raw_data={}, error_count=1, error_details="x")],
            model_name="X",
        )
        assert result.total == 2

    def test_rejection_rate_property(self):
        result = ValidationResult(
            valid=[_SampleRecord(name="a", value=1)],
            rejected=[RejectedRecord(raw_data={}, error_count=1, error_details="x")],
            model_name="X",
        )
        assert result.rejection_rate == pytest.approx(0.5)

    def test_rejection_rate_empty(self):
        result = ValidationResult(valid=[], rejected=[], model_name="X")
        assert result.rejection_rate == 0.0


# ---------------------------------------------------------------------------
# Test 6: RejectedRecord fields
# ---------------------------------------------------------------------------


class TestRejectedRecordFields:
    """RejectedRecord contains raw_data, error_count, error_details."""

    def test_fields_present(self):
        rec = RejectedRecord(raw_data={"a": 1}, error_count=3, error_details="details")
        assert rec.raw_data == {"a": 1}
        assert rec.error_count == 3
        assert rec.error_details == "details"


# ---------------------------------------------------------------------------
# Tests 1-3: validate_records
# ---------------------------------------------------------------------------


class TestValidateRecords:
    """validate_records validates dicts against a Pydantic model."""

    def test_all_valid_records(self):
        """Test 1: valid dicts -> all in .valid, empty .rejected."""
        raw = [{"name": "alpha", "value": 10}, {"name": "beta", "value": 20}]
        result = validate_records(raw, _SampleRecord)
        assert len(result.valid) == 2
        assert len(result.rejected) == 0
        assert result.model_name == "_SampleRecord"

    def test_malformed_record_rejected(self):
        """Test 2: missing required field -> in .rejected with error info."""
        raw = [{"name": "alpha"}]  # missing 'value'
        result = validate_records(raw, _SampleRecord)
        assert len(result.valid) == 0
        assert len(result.rejected) == 1
        assert result.rejected[0].error_count >= 1
        assert "value" in result.rejected[0].error_details.lower()

    def test_mixed_valid_and_invalid(self):
        """Test 3: mixed records -> both .valid and .rejected populated."""
        raw = [
            {"name": "good", "value": 1},
            {"value": "not_an_int"},  # missing name, wrong type
            {"name": "also_good", "value": 2},
        ]
        result = validate_records(raw, _SampleRecord)
        assert len(result.valid) == 2
        assert len(result.rejected) == 1


# ---------------------------------------------------------------------------
# Test 4: structlog warning on rejection
# ---------------------------------------------------------------------------


class TestValidateRecordsLogging:
    """validate_records logs structlog warnings for rejected records."""

    def test_logs_warning_for_rejected(self):
        """Test 4: structlog warning is emitted per rejected record."""
        import structlog
        from structlog.testing import capture_logs

        with capture_logs() as cap_logs:
            result = validate_records([{"name": "x"}], _SampleRecord)

        assert len(result.rejected) == 1
        warning_events = [e for e in cap_logs if e.get("log_level") == "warning"]
        assert any("record_rejected" in e.get("event", "") for e in warning_events)


# ---------------------------------------------------------------------------
# Tests 7-8: validate_score_range
# ---------------------------------------------------------------------------


class TestValidateScoreRange:
    """validate_score_range enforces 0-100 range."""

    def test_rejects_below_zero(self):
        """Test 7a: score < 0 raises ValueError."""
        with pytest.raises(ValueError, match="score"):
            validate_score_range(-1)

    def test_rejects_above_100(self):
        """Test 7b: score > 100 raises ValueError."""
        with pytest.raises(ValueError, match="score"):
            validate_score_range(101)

    def test_accepts_boundary_zero(self):
        """Test 8a: score = 0 is valid."""
        assert validate_score_range(0) == 0

    def test_accepts_boundary_100(self):
        """Test 8b: score = 100 is valid."""
        assert validate_score_range(100) == 100

    def test_accepts_midrange(self):
        """Normal score in range."""
        assert validate_score_range(50) == 50

    def test_returns_int_from_float(self):
        """Float input is converted to int."""
        assert validate_score_range(75.9) == 75
        assert isinstance(validate_score_range(75.9), int)

    def test_custom_field_name_in_error(self):
        """Custom field_name appears in error message."""
        with pytest.raises(ValueError, match="composite_score"):
            validate_score_range(-5, field_name="composite_score")
