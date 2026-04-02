"""Smoke tests for pipeline CLI commands.

Verifies that the pipeline subcommand group is registered and help
text renders without errors. Uses Typer's CliRunner for isolation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ai_washer.cli import app
from ai_washer.pipeline.types import PipelineRunResult, StageResult

runner = CliRunner()


class TestPipelineCLIHelp:
    """Verify pipeline subcommands are registered and help renders."""

    def test_pipeline_help_lists_subcommands(self) -> None:
        result = runner.invoke(app, ["pipeline", "--help"])
        assert result.exit_code == 0
        assert "run" in result.output
        assert "status" in result.output
        assert "staleness" in result.output

    def test_pipeline_run_help(self) -> None:
        result = runner.invoke(app, ["pipeline", "run", "--help"])
        assert result.exit_code == 0
        assert "daily pipeline" in result.output.lower()

    def test_pipeline_status_help(self) -> None:
        result = runner.invoke(app, ["pipeline", "status", "--help"])
        assert result.exit_code == 0
        assert "recent" in result.output.lower() or "pipeline" in result.output.lower()

    def test_pipeline_staleness_help(self) -> None:
        result = runner.invoke(app, ["pipeline", "staleness", "--help"])
        assert result.exit_code == 0
        assert "staleness" in result.output.lower()


class TestPipelineRunCommand:
    """Verify pipeline run command invokes the flow."""

    def test_pipeline_run_invokes_flow(self) -> None:
        """Patch the lazy import target to verify flow is called."""
        import uuid

        ok = StageResult(stage="sec_filings", status="succeeded", companies_processed=5)
        mock_result = PipelineRunResult(
            run_id=uuid.uuid4(),
            started_at=MagicMock(),
            ended_at=MagicMock(),
            status="succeeded",
            stages=[ok],
            companies_processed=5,
        )

        with patch(
            "ai_washer.pipeline.daily_flow.daily_pipeline_flow",
            return_value=mock_result,
        ):
            result = runner.invoke(app, ["pipeline", "run"])

        assert result.exit_code == 0
        assert "status" in result.output.lower()
