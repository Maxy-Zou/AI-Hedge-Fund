"""Unit tests for CLI github subcommands.

Tests verify that the github collect and collect-all commands are
registered and show help text via the Typer test runner.
"""

from __future__ import annotations

from typer.testing import CliRunner

from ai_washer.cli import app

runner = CliRunner()


class TestGitHubCLICommands:
    """Test github CLI subcommand registration."""

    def test_github_help_shows_commands(self) -> None:
        """github --help lists collect and collect-all."""
        result = runner.invoke(app, ["github", "--help"])
        assert result.exit_code == 0
        assert "collect" in result.output
        assert "collect-all" in result.output

    def test_github_collect_help(self) -> None:
        """github collect --help shows usage."""
        result = runner.invoke(app, ["github", "collect", "--help"])
        assert result.exit_code == 0
        assert "IDENTIFIER" in result.output or "identifier" in result.output.lower()

    def test_github_collect_all_help(self) -> None:
        """github collect-all --help shows usage."""
        result = runner.invoke(app, ["github", "collect-all", "--help"])
        assert result.exit_code == 0
        assert "dry-run" in result.output.lower()
