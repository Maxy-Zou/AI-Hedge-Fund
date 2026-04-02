"""Unit tests for CLI universe subcommands (scan, list, inspect).

Tests use CliRunner with mocked database sessions and builder to
avoid real API calls and database connections.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ai_washer.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_company(
    ticker: str = "TEST",
    name: str = "Test Corp",
    cik: str = "1234567",
    market_cap_cents: int | None = 500_000_000_000,
    is_active: bool = True,
    aliases: dict | None = None,
    sector: str | None = None,
    deactivation_reason: str | None = None,
) -> MagicMock:
    """Build a mock Company object with the given attributes."""
    company = MagicMock()
    company.id = uuid.uuid4()
    company.ticker = ticker
    company.name = name
    company.cik = cik
    company.market_cap_cents = market_cap_cents
    company.is_active = is_active
    company.aliases = aliases or {"cik": cik}
    company.sector = sector
    company.deactivation_reason = deactivation_reason
    company.created_at = datetime(2026, 3, 27, tzinfo=timezone.utc)
    company.updated_at = datetime(2026, 3, 27, tzinfo=timezone.utc)
    return company


# ---------------------------------------------------------------------------
# universe --help
# ---------------------------------------------------------------------------


class TestUniverseHelp:
    """Tests for the universe subcommand group help output."""

    def test_universe_help_shows_subcommands(self):
        result = runner.invoke(app, ["universe", "--help"])
        assert result.exit_code == 0
        assert "scan" in result.output
        assert "list" in result.output
        assert "inspect" in result.output

    def test_universe_help_shows_description(self):
        result = runner.invoke(app, ["universe", "--help"])
        assert "Manage the target company universe" in result.output


# ---------------------------------------------------------------------------
# universe scan
# ---------------------------------------------------------------------------


class TestUniverseScan:
    """Tests for the universe scan command."""

    @patch("ai_washer.universe.builder.UniverseBuilder")
    @patch("ai_washer.config.UniverseSettings")
    @patch("ai_washer.config.load_app_settings")
    def test_scan_dry_run(self, mock_load, mock_settings, mock_builder_cls):
        mock_load.return_value = MagicMock()
        mock_settings.return_value = MagicMock()

        mock_builder = MagicMock()
        mock_builder.scan.return_value = [MagicMock()] * 15
        mock_builder.filter_market_cap.return_value = [MagicMock()] * 8
        mock_builder_cls.return_value = mock_builder

        result = runner.invoke(app, ["universe", "scan", "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "15 unique companies" in result.output
        assert "8 companies" in result.output
        assert "No database changes" in result.output

    @patch("ai_washer.universe.builder.UniverseBuilder")
    @patch("ai_washer.config.UniverseSettings")
    @patch("ai_washer.config.load_app_settings")
    def test_scan_full_run(self, mock_load, mock_settings, mock_builder_cls):
        from ai_washer.universe.builder import UniverseBuildResult

        mock_load.return_value = MagicMock()
        mock_settings.return_value = MagicMock()

        mock_builder = MagicMock()
        mock_builder.build.return_value = UniverseBuildResult(
            scan_date=date(2026, 3, 27),
            company_count=12,
            new_count=5,
            updated_count=4,
            deactivated_count=3,
            skipped_no_market_cap=7,
        )
        mock_builder_cls.return_value = mock_builder

        result = runner.invoke(app, ["universe", "scan"])

        assert result.exit_code == 0
        assert "Starting universe scan" in result.output
        assert "2026-03-27" in result.output
        assert "12" in result.output
        assert "New: 5" in result.output
        assert "Updated: 4" in result.output
        assert "Deactivated: 3" in result.output


# ---------------------------------------------------------------------------
# universe list
# ---------------------------------------------------------------------------


class TestUniverseList:
    """Tests for the universe list command."""

    @patch("ai_washer.db.session.get_session_factory")
    @patch("ai_washer.db.session.create_engine_from_settings")
    @patch("ai_washer.config.load_app_settings")
    def test_list_active_companies(self, mock_load, mock_engine, mock_factory):
        mock_load.return_value = MagicMock()
        mock_engine.return_value = MagicMock()

        companies = [
            _make_company(ticker="AAPL", name="Apple Inc", cik="320193"),
            _make_company(ticker="MSFT", name="Microsoft Corp", cik="789019"),
        ]

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = (
            companies
        )
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_session)

        result = runner.invoke(app, ["universe", "list"])

        assert result.exit_code == 0
        assert "AAPL" in result.output
        assert "MSFT" in result.output
        assert "Showing 2 companies" in result.output

    @patch("ai_washer.db.session.get_session_factory")
    @patch("ai_washer.db.session.create_engine_from_settings")
    @patch("ai_washer.config.load_app_settings")
    def test_list_empty_universe(self, mock_load, mock_engine, mock_factory):
        mock_load.return_value = MagicMock()
        mock_engine.return_value = MagicMock()

        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_session)

        result = runner.invoke(app, ["universe", "list"])

        assert result.exit_code == 0
        assert "Showing 0 companies" in result.output


# ---------------------------------------------------------------------------
# universe inspect
# ---------------------------------------------------------------------------


class TestUniverseInspect:
    """Tests for the universe inspect command."""

    @patch("ai_washer.db.session.get_session_factory")
    @patch("ai_washer.db.session.create_engine_from_settings")
    @patch("ai_washer.config.load_app_settings")
    def test_inspect_found(self, mock_load, mock_engine, mock_factory):
        mock_load.return_value = MagicMock()
        mock_engine.return_value = MagicMock()

        company = _make_company(
            ticker="AAPL",
            name="Apple Inc",
            cik="320193",
            sector="Technology",
            aliases={
                "cik": "0000320193",
                "patent_assignee": ["Apple Inc."],
                "github_org": "apple",
            },
        )

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = company
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_session)

        result = runner.invoke(app, ["universe", "inspect", "AAPL"])

        assert result.exit_code == 0
        assert "Ticker:    AAPL" in result.output
        assert "Name:      Apple Inc" in result.output
        assert "CIK:       320193" in result.output
        assert "Sector:    Technology" in result.output
        assert "Active:    True" in result.output
        assert "Aliases:" in result.output
        assert "patent_assignee" in result.output

    @patch("ai_washer.db.session.get_session_factory")
    @patch("ai_washer.db.session.create_engine_from_settings")
    @patch("ai_washer.config.load_app_settings")
    def test_inspect_not_found(self, mock_load, mock_engine, mock_factory):
        mock_load.return_value = MagicMock()
        mock_engine.return_value = MagicMock()

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_session)

        result = runner.invoke(app, ["universe", "inspect", "NOTFOUND"])

        assert result.exit_code == 1
        assert "Company not found: NOTFOUND" in result.output

    @patch("ai_washer.db.session.get_session_factory")
    @patch("ai_washer.db.session.create_engine_from_settings")
    @patch("ai_washer.config.load_app_settings")
    def test_inspect_deactivated_company(self, mock_load, mock_engine, mock_factory):
        mock_load.return_value = MagicMock()
        mock_engine.return_value = MagicMock()

        company = _make_company(
            ticker="DEAC",
            name="Deactivated Corp",
            is_active=False,
            deactivation_reason="not_in_scan_2026-03-27",
        )

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = company
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_session)

        result = runner.invoke(app, ["universe", "inspect", "DEAC"])

        assert result.exit_code == 0
        assert "Active:    False" in result.output
        assert "Deactivation: not_in_scan_2026-03-27" in result.output
