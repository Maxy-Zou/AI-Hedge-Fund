"""Tests for daily pipeline flow orchestration (OPS-03).

Verifies that daily_pipeline_flow calls stages in order, isolates errors
per stage, and produces correct PipelineRunResult.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from ai_washer.pipeline.types import PipelineRunResult, StageResult


# ---------------------------------------------------------------------------
# Test stage functions (stages.py)
# ---------------------------------------------------------------------------


class TestCollectSecFilingsStage:
    """Tests for collect_sec_filings_stage."""

    @patch("ai_washer.ingestion.filing_collector.FilingCollector")
    def test_returns_succeeded_on_success(self, mock_cls: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.filing_count = 5
        mock_result.xbrl_fact_count = 10
        mock_result.errors = []
        mock_cls.return_value.collect_all.return_value = [mock_result]

        from ai_washer.pipeline.stages import collect_sec_filings_stage

        settings = MagicMock()
        result = collect_sec_filings_stage(settings)

        assert result.stage == "sec_filings"
        assert result.status == "succeeded"
        assert result.companies_processed == 1

    @patch("ai_washer.ingestion.filing_collector.FilingCollector")
    def test_returns_failed_on_exception(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.collect_all.side_effect = RuntimeError("SEC down")

        from ai_washer.pipeline.stages import collect_sec_filings_stage

        settings = MagicMock()
        result = collect_sec_filings_stage(settings)

        assert result.stage == "sec_filings"
        assert result.status == "failed"
        assert "SEC down" in result.errors[0]


class TestCollectPatentsStage:
    """Tests for collect_patents_stage."""

    @patch("ai_washer.ingestion.patent_collector.PatentCollector")
    def test_returns_succeeded(self, mock_cls: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.patent_count = 3
        mock_result.errors = []
        mock_cls.return_value.collect_all.return_value = [mock_result]

        from ai_washer.pipeline.stages import collect_patents_stage

        result = collect_patents_stage(MagicMock())

        assert result.stage == "patents"
        assert result.status == "succeeded"

    @patch("ai_washer.ingestion.patent_collector.PatentCollector")
    def test_returns_failed_on_exception(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.collect_all.side_effect = RuntimeError("Patent API down")

        from ai_washer.pipeline.stages import collect_patents_stage

        result = collect_patents_stage(MagicMock())

        assert result.stage == "patents"
        assert result.status == "failed"
        assert "Patent API down" in result.errors[0]


class TestScoreAllStage:
    """Tests for score_all_stage."""

    @patch("ai_washer.analysis.scoring_orchestrator.ScoringOrchestrator")
    @patch("ai_washer.config.ScoringConfig")
    def test_returns_succeeded(self, mock_cfg: MagicMock, mock_cls: MagicMock) -> None:
        mock_cls.return_value.score_all.return_value = [("AAPL", [MagicMock()])]

        from ai_washer.pipeline.stages import score_all_stage

        session = MagicMock()
        run_id = uuid.uuid4()
        result = score_all_stage(session, run_id)

        assert result.stage == "scoring"
        assert result.status == "succeeded"
        assert result.companies_processed == 1


# ---------------------------------------------------------------------------
# Test daily pipeline flow
# ---------------------------------------------------------------------------


_FLOW_PATCHES = [
    "ai_washer.pipeline.daily_flow.load_app_settings",
    "ai_washer.pipeline.daily_flow.create_engine_from_settings",
    "ai_washer.pipeline.daily_flow.get_session_factory",
    "ai_washer.pipeline.daily_flow.update_source_status",
    "ai_washer.pipeline.daily_flow.mark_stale_runs",
    "ai_washer.pipeline.daily_flow.start_pipeline_run",
    "ai_washer.pipeline.daily_flow.end_pipeline_run",
    "ai_washer.pipeline.daily_flow.collect_sec_filings_stage",
    "ai_washer.pipeline.daily_flow.collect_patents_stage",
    "ai_washer.pipeline.daily_flow.collect_github_stage",
    "ai_washer.pipeline.daily_flow.collect_earnings_stage",
    "ai_washer.pipeline.daily_flow.collect_jobs_stage",
    "ai_washer.pipeline.daily_flow.score_all_stage",
    "ai_washer.pipeline.daily_flow.compute_composites_stage",
]


@pytest.fixture()
def flow_mocks():
    """Patch all daily_flow dependencies and return a dict of mocks."""
    patches = {name.rsplit(".", 1)[-1]: patch(name) for name in _FLOW_PATCHES}
    mocks = {}
    for key, p in patches.items():
        mocks[key] = p.start()
    yield mocks
    for p in patches.values():
        p.stop()


def _setup_flow_mocks(mocks: dict, stage_overrides: dict | None = None) -> uuid.UUID:
    """Configure default mock behavior for flow tests."""
    run_id = uuid.uuid4()
    mocks["start_pipeline_run"].return_value = run_id

    mock_session = MagicMock()
    mocks["get_session_factory"].return_value.return_value.__enter__ = MagicMock(
        return_value=mock_session
    )
    mocks["get_session_factory"].return_value.return_value.__exit__ = MagicMock(
        return_value=False
    )

    ok = StageResult(stage="test", status="succeeded", companies_processed=5)
    for key in [
        "collect_sec_filings_stage",
        "collect_patents_stage",
        "collect_github_stage",
        "collect_earnings_stage",
        "collect_jobs_stage",
        "score_all_stage",
        "compute_composites_stage",
    ]:
        mocks[key].return_value = ok

    if stage_overrides:
        for key, val in stage_overrides.items():
            mocks[key].return_value = val

    return run_id


class TestDailyPipelineFlow:
    """Tests for daily_pipeline_flow orchestration."""

    def test_calls_all_stages_in_order(self, flow_mocks: dict) -> None:
        run_id = _setup_flow_mocks(flow_mocks)
        ok = StageResult(stage="test", status="succeeded", companies_processed=5)

        flow_mocks["end_pipeline_run"].return_value = PipelineRunResult(
            run_id=run_id,
            started_at=MagicMock(),
            ended_at=MagicMock(),
            status="succeeded",
            stages=[ok] * 7,
            companies_processed=5,
        )

        from ai_washer.pipeline.daily_flow import daily_pipeline_flow

        result = daily_pipeline_flow.fn()

        flow_mocks["mark_stale_runs"].assert_called_once()
        flow_mocks["start_pipeline_run"].assert_called_once()
        flow_mocks["collect_sec_filings_stage"].assert_called_once()
        flow_mocks["collect_patents_stage"].assert_called_once()
        flow_mocks["collect_github_stage"].assert_called_once()
        flow_mocks["collect_earnings_stage"].assert_called_once()
        flow_mocks["collect_jobs_stage"].assert_called_once()
        flow_mocks["score_all_stage"].assert_called_once()
        flow_mocks["end_pipeline_run"].assert_called_once()
        assert result.status == "succeeded"

    def test_continues_scoring_when_ingestion_fails(self, flow_mocks: dict) -> None:
        fail = StageResult(stage="patents", status="failed", errors=["Patent API down"])
        run_id = _setup_flow_mocks(flow_mocks, {"collect_patents_stage": fail})
        ok = StageResult(stage="test", status="succeeded", companies_processed=5)

        flow_mocks["end_pipeline_run"].return_value = PipelineRunResult(
            run_id=run_id,
            started_at=MagicMock(),
            ended_at=MagicMock(),
            status="partially_failed",
            stages=[ok, fail, ok, ok, ok, ok, ok],
            companies_processed=5,
        )

        from ai_washer.pipeline.daily_flow import daily_pipeline_flow

        result = daily_pipeline_flow.fn()

        # Scoring still ran even though patents failed
        flow_mocks["score_all_stage"].assert_called_once()
        assert result.status == "partially_failed"

    def test_calls_update_source_status_per_ingestion_stage(self, flow_mocks: dict) -> None:
        run_id = _setup_flow_mocks(flow_mocks)
        ok = StageResult(stage="test", status="succeeded", companies_processed=5)

        flow_mocks["end_pipeline_run"].return_value = PipelineRunResult(
            run_id=run_id,
            started_at=MagicMock(),
            ended_at=MagicMock(),
            status="succeeded",
            stages=[ok] * 7,
            companies_processed=5,
        )

        from ai_washer.pipeline.daily_flow import daily_pipeline_flow

        daily_pipeline_flow.fn()

        # 5 ingestion stages should each call update_source_status
        source_names = [c.args[1] for c in flow_mocks["update_source_status"].call_args_list]
        assert "sec_filings" in source_names
        assert "patents" in source_names
        assert "github" in source_names
        assert "earnings" in source_names
        assert "jobs" in source_names

    def test_all_stages_fail_returns_failed(self, flow_mocks: dict) -> None:
        fail = StageResult(stage="test", status="failed", errors=["down"])
        run_id = _setup_flow_mocks(
            flow_mocks,
            {
                "collect_sec_filings_stage": fail,
                "collect_patents_stage": fail,
                "collect_github_stage": fail,
                "collect_earnings_stage": fail,
                "collect_jobs_stage": fail,
                "score_all_stage": fail,
                "compute_composites_stage": fail,
            },
        )

        flow_mocks["end_pipeline_run"].return_value = PipelineRunResult(
            run_id=run_id,
            started_at=MagicMock(),
            ended_at=MagicMock(),
            status="failed",
            stages=[fail] * 7,
            companies_processed=0,
        )

        from ai_washer.pipeline.daily_flow import daily_pipeline_flow

        result = daily_pipeline_flow.fn()

        assert result.status == "failed"

    def test_marks_stale_runs_at_start(self, flow_mocks: dict) -> None:
        run_id = _setup_flow_mocks(flow_mocks)
        ok = StageResult(stage="test", status="succeeded", companies_processed=5)

        flow_mocks["end_pipeline_run"].return_value = PipelineRunResult(
            run_id=run_id,
            started_at=MagicMock(),
            ended_at=MagicMock(),
            status="succeeded",
            stages=[ok] * 7,
            companies_processed=5,
        )

        from ai_washer.pipeline.daily_flow import daily_pipeline_flow

        daily_pipeline_flow.fn()

        flow_mocks["mark_stale_runs"].assert_called_once()
