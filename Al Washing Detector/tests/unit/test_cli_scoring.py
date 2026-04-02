"""Tests for CLI score commands using typer.testing.CliRunner.

CLI functions use lazy imports, so we must pre-import the modules and then
patch the names within those modules before invoking the CLI.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ai_washer.cli import app

runner = CliRunner()


@pytest.fixture
def mock_company():
    """Create a mock Company ORM object."""
    company = MagicMock()
    company.id = uuid.UUID("12345678-1234-1234-1234-123456789abc")
    company.ticker = "TEST"
    company.cik = "0001234567"
    company.name = "Test Corp"
    company.is_active = True
    return company


class TestScoreCompanyCmd:
    """Tests for 'score company' CLI command."""

    def test_score_help_shows_commands(self):
        """Test that 'score --help' lists company and all subcommands."""
        result = runner.invoke(app, ["score", "--help"])
        assert result.exit_code == 0
        assert "company" in result.output
        assert "all" in result.output

    def test_score_company_help(self):
        """Test that 'score company --help' shows expected options."""
        result = runner.invoke(app, ["score", "company", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--date" in result.output
        assert "IDENTIFIER" in result.output

    def test_score_all_help(self):
        """Test that 'score all --help' shows expected options."""
        result = runner.invoke(app, ["score", "all", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--date" in result.output


class TestScoreCompanyIntegration:
    """Higher-level tests for score_company_cmd function logic."""

    def test_score_company_with_no_data_returns_no_scores(self, mock_company):
        """When orchestrator returns no results, CLI prints insufficient data message."""
        from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator
        from ai_washer.config import load_app_settings, load_scoring_config
        from ai_washer.db.session import create_engine_from_settings, get_session_factory

        mock_session = MagicMock()
        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_company
        mock_session.execute.return_value = mock_session_result

        # Build context manager
        mock_sf_instance = MagicMock()
        mock_sf_instance.__enter__ = MagicMock(return_value=mock_session)
        mock_sf_instance.__exit__ = MagicMock(return_value=False)

        mock_orch = MagicMock()
        mock_orch.score_company.return_value = []

        with (
            patch.object(
                type(load_app_settings), "__call__",
                return_value=MagicMock(),
                create=True,
            ) if False else patch(
                "ai_washer.config.load_app_settings",
                return_value=MagicMock(),
            ),
            patch(
                "ai_washer.config.load_scoring_config",
                return_value=MagicMock(),
            ),
            patch(
                "ai_washer.db.session.create_engine_from_settings",
                return_value=MagicMock(),
            ),
            patch(
                "ai_washer.db.session.get_session_factory",
                return_value=MagicMock(return_value=mock_sf_instance),
            ),
            patch(
                "ai_washer.analysis.scoring_orchestrator.ScoringOrchestrator",
                return_value=mock_orch,
            ),
        ):
            result = runner.invoke(app, ["score", "company", "TEST"])
            assert result.exit_code == 0
            assert "No scores produced" in result.output

    def test_score_company_dry_run_does_not_persist(self, mock_company):
        """--dry-run computes scores but never calls persist."""
        from ai_washer.analysis.types import SignalResult

        mock_session = MagicMock()
        mock_session_result = MagicMock()
        mock_session_result.scalar_one_or_none.return_value = mock_company
        mock_session.execute.return_value = mock_session_result

        mock_sf_instance = MagicMock()
        mock_sf_instance.__enter__ = MagicMock(return_value=mock_session)
        mock_sf_instance.__exit__ = MagicMock(return_value=False)

        mock_orch = MagicMock()
        mock_orch.score_company.return_value = [
            SignalResult(
                signal_type="sec_filing",
                score=65,
                evidence={"signal_version": "0.4.0"},
            ),
        ]

        with (
            patch(
                "ai_washer.config.load_app_settings",
                return_value=MagicMock(),
            ),
            patch(
                "ai_washer.config.load_scoring_config",
                return_value=MagicMock(),
            ),
            patch(
                "ai_washer.db.session.create_engine_from_settings",
                return_value=MagicMock(),
            ),
            patch(
                "ai_washer.db.session.get_session_factory",
                return_value=MagicMock(return_value=mock_sf_instance),
            ),
            patch(
                "ai_washer.analysis.scoring_orchestrator.ScoringOrchestrator",
                return_value=mock_orch,
            ),
        ):
            result = runner.invoke(app, ["score", "company", "TEST", "--dry-run"])
            assert result.exit_code == 0
            assert "DRY RUN" in result.output
            mock_orch.persist_signals.assert_not_called()
            mock_session.commit.assert_not_called()


class TestScoreAllIntegration:
    """Tests for score_all_cmd function logic."""

    def test_score_all_dry_run_does_not_commit(self):
        """--dry-run does not commit the session."""
        from ai_washer.analysis.types import SignalResult

        mock_session = MagicMock()

        mock_sf_instance = MagicMock()
        mock_sf_instance.__enter__ = MagicMock(return_value=mock_session)
        mock_sf_instance.__exit__ = MagicMock(return_value=False)

        mock_orch = MagicMock()
        mock_orch.score_all.return_value = [
            (
                "TEST",
                [
                    SignalResult(
                        signal_type="sec_filing",
                        score=65,
                        evidence={},
                    ),
                ],
            ),
        ]

        with (
            patch(
                "ai_washer.config.load_app_settings",
                return_value=MagicMock(),
            ),
            patch(
                "ai_washer.config.load_scoring_config",
                return_value=MagicMock(),
            ),
            patch(
                "ai_washer.db.session.create_engine_from_settings",
                return_value=MagicMock(),
            ),
            patch(
                "ai_washer.db.session.get_session_factory",
                return_value=MagicMock(return_value=mock_sf_instance),
            ),
            patch(
                "ai_washer.analysis.scoring_orchestrator.ScoringOrchestrator",
                return_value=mock_orch,
            ),
        ):
            result = runner.invoke(app, ["score", "all", "--dry-run"])
            assert result.exit_code == 0
            assert "DRY RUN" in result.output
            mock_session.commit.assert_not_called()
