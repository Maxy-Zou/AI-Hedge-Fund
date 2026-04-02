"""Unit tests for CLI filing collection subcommands (collect company, collect all).

Tests use CliRunner with mocked database sessions and FilingCollector to
avoid real API calls and database connections.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ai_washer.cli import app
from ai_washer.ingestion.types import CollectionResult

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_company_mock(
    ticker: str = "AAPL",
    cik: str = "320193",
    company_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a mock Company object."""
    company = MagicMock()
    company.id = company_id or uuid.uuid4()
    company.ticker = ticker
    company.cik = cik
    return company


def _make_collection_result(
    cik: str = "320193",
    filing_count: int = 5,
    xbrl_fact_count: int = 12,
    skipped_count: int = 2,
    errors: list[str] | None = None,
) -> CollectionResult:
    """Build a CollectionResult fixture."""
    return CollectionResult(
        company_cik=cik,
        filing_count=filing_count,
        xbrl_fact_count=xbrl_fact_count,
        skipped_count=skipped_count,
        errors=errors or [],
    )


# ---------------------------------------------------------------------------
# collect --help
# ---------------------------------------------------------------------------


class TestCollectHelp:
    """Tests for the collect subcommand group."""

    def test_collect_help_shows_subcommands(self):
        result = runner.invoke(app, ["collect", "--help"])
        assert result.exit_code == 0
        assert "company" in result.output
        assert "all" in result.output

    def test_collect_help_shows_description(self):
        result = runner.invoke(app, ["collect", "--help"])
        assert "SEC filings" in result.output or "XBRL" in result.output


# ---------------------------------------------------------------------------
# collect company
# ---------------------------------------------------------------------------


class TestCollectCompany:
    """Tests for the collect company command."""

    @patch("ai_washer.ingestion.filing_collector.FilingCollector")
    @patch("ai_washer.db.session.get_session_factory")
    @patch("ai_washer.db.session.create_engine_from_settings")
    @patch("ai_washer.config.load_app_settings")
    def test_collect_company_invokes_collector(
        self, mock_load, mock_engine, mock_factory, mock_collector_cls
    ):
        """Test 1: collect company AAPL invokes FilingCollector.collect_for_company."""
        mock_load.return_value = MagicMock()
        mock_engine.return_value = MagicMock()

        company = _make_company_mock(ticker="AAPL", cik="320193")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = company
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_session)

        mock_collector = MagicMock()
        mock_collector.collect_for_company.return_value = _make_collection_result()
        mock_collector_cls.return_value = mock_collector

        result = runner.invoke(app, ["collect", "company", "AAPL"])

        assert result.exit_code == 0
        mock_collector.collect_for_company.assert_called_once()

    @patch("ai_washer.ingestion.filing_collector.FilingCollector")
    @patch("ai_washer.db.session.get_session_factory")
    @patch("ai_washer.db.session.create_engine_from_settings")
    @patch("ai_washer.config.load_app_settings")
    def test_collect_company_outputs_counts(
        self, mock_load, mock_engine, mock_factory, mock_collector_cls
    ):
        """Test 4: collect company outputs filing_count, xbrl_fact_count, skipped_count."""
        mock_load.return_value = MagicMock()
        mock_engine.return_value = MagicMock()

        company = _make_company_mock(ticker="AAPL", cik="320193")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = company
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_session)

        mock_collector = MagicMock()
        mock_collector.collect_for_company.return_value = _make_collection_result(
            filing_count=5, xbrl_fact_count=12, skipped_count=2
        )
        mock_collector_cls.return_value = mock_collector

        result = runner.invoke(app, ["collect", "company", "AAPL"])

        assert result.exit_code == 0
        assert "5" in result.output
        assert "12" in result.output
        assert "2" in result.output

    @patch("ai_washer.db.session.get_session_factory")
    @patch("ai_washer.db.session.create_engine_from_settings")
    @patch("ai_washer.config.load_app_settings")
    def test_collect_company_dry_run(self, mock_load, mock_engine, mock_factory):
        """Test 3: collect company --dry-run prints what would happen without DB writes."""
        mock_load.return_value = MagicMock()
        mock_engine.return_value = MagicMock()

        company = _make_company_mock(ticker="AAPL", cik="320193")

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = company
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_session)

        result = runner.invoke(app, ["collect", "company", "--dry-run", "AAPL"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "AAPL" in result.output


# ---------------------------------------------------------------------------
# collect all
# ---------------------------------------------------------------------------


class TestCollectAll:
    """Tests for the collect all command."""

    @patch("ai_washer.ingestion.filing_collector.FilingCollector")
    @patch("ai_washer.config.load_app_settings")
    def test_collect_all_invokes_collector(self, mock_load, mock_collector_cls):
        """Test 2: collect all invokes FilingCollector.collect_all."""
        mock_load.return_value = MagicMock()

        mock_collector = MagicMock()
        mock_collector.collect_all.return_value = [
            _make_collection_result(cik="320193"),
            _make_collection_result(cik="789019"),
        ]
        mock_collector_cls.return_value = mock_collector

        result = runner.invoke(app, ["collect", "all"])

        assert result.exit_code == 0
        mock_collector.collect_all.assert_called_once()
        assert "2 companies" in result.output

    @patch("ai_washer.db.session.get_session_factory")
    @patch("ai_washer.db.session.create_engine_from_settings")
    @patch("ai_washer.config.load_app_settings")
    def test_collect_all_dry_run(self, mock_load, mock_engine, mock_factory):
        """Test: collect all --dry-run shows company count without DB writes."""
        mock_load.return_value = MagicMock()
        mock_engine.return_value = MagicMock()

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 15
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_session)

        result = runner.invoke(app, ["collect", "all", "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "15" in result.output
