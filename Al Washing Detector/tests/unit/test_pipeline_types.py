"""Tests for pipeline type contracts and DataSourceStatus model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


class TestStageResult:
    """Tests for StageResult frozen dataclass."""

    def test_stage_result_is_frozen(self) -> None:
        from ai_washer.pipeline.types import StageResult

        result = StageResult(stage="sec_filings", status="success")
        with pytest.raises(AttributeError):
            result.stage = "other"  # type: ignore[misc]

    def test_stage_result_defaults(self) -> None:
        from ai_washer.pipeline.types import StageResult

        result = StageResult(stage="sec_filings", status="success")
        assert result.stage == "sec_filings"
        assert result.status == "success"
        assert result.companies_processed == 0
        assert result.errors == []

    def test_stage_result_with_errors(self) -> None:
        from ai_washer.pipeline.types import StageResult

        result = StageResult(
            stage="patents",
            status="partial",
            companies_processed=5,
            errors=["API timeout", "Rate limited"],
        )
        assert result.companies_processed == 5
        assert len(result.errors) == 2

    def test_stage_result_default_errors_not_shared(self) -> None:
        """Each StageResult should get its own errors list (not shared mutable default)."""
        from ai_washer.pipeline.types import StageResult

        r1 = StageResult(stage="a", status="ok")
        r2 = StageResult(stage="b", status="ok")
        assert r1.errors is not r2.errors


class TestPipelineRunResult:
    """Tests for PipelineRunResult frozen dataclass."""

    def test_pipeline_run_result_fields(self) -> None:
        from ai_washer.pipeline.types import PipelineRunResult, StageResult

        run_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)
        stages = [
            StageResult(stage="sec", status="success", companies_processed=10, errors=["err1"]),
            StageResult(stage="patents", status="success", companies_processed=8, errors=["e2", "e3"]),
        ]
        result = PipelineRunResult(
            run_id=run_id,
            started_at=now,
            ended_at=now,
            status="completed",
            stages=stages,
            companies_processed=10,
        )
        assert result.run_id == run_id
        assert result.status == "completed"
        assert result.companies_processed == 10

    def test_total_errors_computed_from_stages(self) -> None:
        from ai_washer.pipeline.types import PipelineRunResult, StageResult

        stages = [
            StageResult(stage="sec", status="ok", errors=["e1"]),
            StageResult(stage="patents", status="ok", errors=["e2", "e3"]),
        ]
        result = PipelineRunResult(
            run_id=uuid.uuid4(),
            started_at=datetime.now(tz=timezone.utc),
            ended_at=datetime.now(tz=timezone.utc),
            status="completed",
            stages=stages,
            companies_processed=5,
        )
        assert result.total_errors == 3

    def test_total_errors_zero_when_no_errors(self) -> None:
        from ai_washer.pipeline.types import PipelineRunResult, StageResult

        stages = [StageResult(stage="sec", status="ok")]
        result = PipelineRunResult(
            run_id=uuid.uuid4(),
            started_at=datetime.now(tz=timezone.utc),
            ended_at=datetime.now(tz=timezone.utc),
            status="completed",
            stages=stages,
            companies_processed=0,
        )
        assert result.total_errors == 0

    def test_pipeline_run_result_is_frozen(self) -> None:
        from ai_washer.pipeline.types import PipelineRunResult

        result = PipelineRunResult(
            run_id=uuid.uuid4(),
            started_at=datetime.now(tz=timezone.utc),
            ended_at=datetime.now(tz=timezone.utc),
            status="ok",
            stages=[],
            companies_processed=0,
        )
        with pytest.raises(AttributeError):
            result.status = "failed"  # type: ignore[misc]


class TestDataSourceStatusModel:
    """Tests for DataSourceStatus ORM model structure."""

    def test_data_source_status_tablename(self) -> None:
        from ai_washer.db.models import DataSourceStatus

        assert DataSourceStatus.__tablename__ == "data_source_status"

    def test_data_source_status_columns(self) -> None:
        from ai_washer.db.models import DataSourceStatus

        columns = DataSourceStatus.__table__.columns
        expected = {
            "id",
            "source_name",
            "last_success_at",
            "last_error_at",
            "last_error_message",
            "expected_cadence_hours",
            "is_stale",
            "updated_at",
        }
        assert set(columns.keys()) == expected

    def test_source_name_is_unique(self) -> None:
        from ai_washer.db.models import DataSourceStatus

        col = DataSourceStatus.__table__.columns["source_name"]
        assert col.unique is True

    def test_is_stale_default_false(self) -> None:
        from ai_washer.db.models import DataSourceStatus

        col = DataSourceStatus.__table__.columns["is_stale"]
        assert col.server_default is not None
