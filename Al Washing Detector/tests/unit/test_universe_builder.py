"""Unit tests for universe builder orchestrator.

Tests the full pipeline: EFTS scan -> deduplication -> market cap filter
-> entity resolution -> database persistence, with mock dependencies
injected for isolated testing.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import JSON, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from ai_washer.db.base import Base
from ai_washer.db.models import Company
from ai_washer.entity.types import (
    AliasesSchema,
    EntityResolutionResult,
    ResolutionMetadata,
    ResolutionMethod,
)
from ai_washer.universe.builder import UniverseBuilder, UniverseBuildResult, build_universe
from ai_washer.universe.types import EFTSHit, MarketCapRange


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_hit(
    entity_name: str = "TEST CORP",
    ciks: list[str] | None = None,
    accession_no: str = "0000000000-00-000001",
    form_type: str = "10-K",
    file_date: str = "2025-12-01",
) -> EFTSHit:
    """Build a minimal EFTSHit for testing."""
    return EFTSHit(
        accession_no=accession_no,
        form_type=form_type,
        file_date=file_date,
        entity_name=entity_name,
        ciks=ciks or ["12345"],
    )


def _make_resolution(
    sec_name: str,
    cik: str,
    ticker: str | None = None,
) -> EntityResolutionResult:
    """Build a minimal EntityResolutionResult for testing."""
    return EntityResolutionResult(
        sec_name=sec_name,
        matched_cik=cik,
        ticker=ticker,
        resolved_aliases=AliasesSchema(
            cik=cik,
            resolution_metadata=ResolutionMetadata(
                resolved_at=date(2025, 12, 1),
                method=ResolutionMethod.AUTOMATED_FUZZY,
                confidence=0.9,
                needs_review=False,
            ),
        ),
    )


@pytest.fixture
def mock_efts():
    """Mock EFTSClient with search_filings returning canned hits."""
    client = MagicMock()
    client.search_filings.return_value = [
        _make_hit("ALPHA INC", ciks=["100"], file_date="2025-12-01"),
        _make_hit("BETA CORP", ciks=["200"], file_date="2025-11-15"),
        _make_hit("GAMMA LLC", ciks=["300"], file_date="2025-10-20"),
    ]
    return client


@pytest.fixture
def mock_edgar():
    """Mock EdgarFactsClient with public float and ticker mapping."""
    client = MagicMock()
    client.get_entity_public_float_batch.return_value = {
        "100": 500_000_000_000,   # $5B -- in range
        "200": 300_000_000_000,   # $3B -- in range
        "300": 50_000_000_000,    # $500M -- below min, should be filtered
    }
    client.get_cik_ticker_mapping.return_value = {
        "100": ("ALPH", "Alpha Inc"),
        "200": ("BETA", "Beta Corp"),
        "300": ("GAMM", "Gamma LLC"),
    }
    return client


@pytest.fixture
def mock_resolver():
    """Mock EntityResolver that returns canned resolution results."""
    resolver = MagicMock()

    def _resolve_side_effect(sec_name, cik, candidates=None, ticker=None):
        return _make_resolution(sec_name=sec_name, cik=cik, ticker=ticker)

    resolver.resolve_entity.side_effect = _resolve_side_effect
    return resolver


@pytest.fixture
def universe_settings():
    """Default UniverseSettings for tests."""
    from ai_washer.config import UniverseSettings

    return UniverseSettings(
        ai_keywords=["artificial intelligence", "machine learning"],
        market_cap_min_cents=150_000_000_000,
        market_cap_max_cents=900_000_000_000,
    )


@pytest.fixture
def app_settings():
    """Minimal AppSettings for tests."""
    from ai_washer.config import AppSettings

    return AppSettings(
        database_url="sqlite:///:memory:",
        edgar_identity="TestCorp test@example.com",
    )


@pytest.fixture
def sqlite_session_factory():
    """In-memory SQLite session factory for persistence tests.

    Registers JSONB->JSON type adapter since SQLite has no native JSONB.
    """
    engine = create_engine("sqlite:///:memory:")

    # Map PostgreSQL JSONB to generic JSON for SQLite compatibility
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        pass  # Placeholder for future pragmas

    # Patch JSONB columns to use JSON for this engine
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def builder(
    universe_settings,
    app_settings,
    mock_efts,
    mock_edgar,
    mock_resolver,
    sqlite_session_factory,
):
    """UniverseBuilder with all dependencies mocked."""
    return UniverseBuilder(
        settings=universe_settings,
        app_settings=app_settings,
        efts_client=mock_efts,
        edgar_client=mock_edgar,
        entity_resolver=mock_resolver,
        session_factory=sqlite_session_factory,
    )


# ---------------------------------------------------------------------------
# Scan tests
# ---------------------------------------------------------------------------


class TestScan:
    """Tests for the scan phase of universe building."""

    def test_scan_calls_efts_for_each_keyword(self, builder, mock_efts) -> None:
        """scan() searches each keyword separately per Pitfall 1."""
        builder.scan(scan_date=date(2025, 12, 15))
        assert mock_efts.search_filings.call_count == 2  # 2 keywords

    def test_scan_uses_quoted_keywords(self, builder, mock_efts) -> None:
        """Keywords are wrapped in double quotes for exact phrase match."""
        builder.scan(scan_date=date(2025, 12, 15))
        calls = mock_efts.search_filings.call_args_list
        queries = [c.kwargs.get("query") or c.args[0] for c in calls]
        for q in queries:
            assert q.startswith('"') and q.endswith('"')

    def test_scan_deduplicates_combined_hits(self, builder, mock_efts) -> None:
        """Hits from multiple keyword searches are deduplicated by CIK."""
        # Both keywords return the same 3 hits
        hits = builder.scan(scan_date=date(2025, 12, 15))
        # 6 raw hits (3 per keyword), deduplicated to 3 unique CIKs
        assert len(hits) == 3

    def test_scan_uses_12_month_window(self, builder, mock_efts) -> None:
        """Date range spans 12 months back from scan_date."""
        builder.scan(scan_date=date(2025, 12, 15))
        calls = mock_efts.search_filings.call_args_list
        first_call = calls[0]
        assert first_call.kwargs.get("date_start") == "2024-12-15"
        assert first_call.kwargs.get("date_end") == "2025-12-15"


# ---------------------------------------------------------------------------
# Market cap filter tests
# ---------------------------------------------------------------------------


class TestFilterMarketCap:
    """Tests for market cap filtering phase."""

    def test_filter_removes_companies_outside_range(self, builder) -> None:
        """Companies below min or above max are excluded."""
        hits = [
            _make_hit("ALPHA INC", ciks=["100"]),
            _make_hit("BETA CORP", ciks=["200"]),
            _make_hit("GAMMA LLC", ciks=["300"]),
        ]
        result = builder.filter_market_cap(hits)
        # Only 100 ($5B) and 200 ($3B) pass; 300 ($500M) is below min
        assert len(result) == 2
        ciks = [h.ciks[0] for h, _ in result]
        assert "100" in ciks
        assert "200" in ciks


# ---------------------------------------------------------------------------
# Entity resolution tests
# ---------------------------------------------------------------------------


class TestResolveEntities:
    """Tests for entity resolution phase."""

    def test_resolve_calls_resolver_for_each_company(
        self, builder, mock_resolver
    ) -> None:
        """resolve_entities calls EntityResolver.resolve_entity for each hit."""
        hits_with_cap = [
            (_make_hit("ALPHA", ciks=["100"]), 500_000_000_000),
            (_make_hit("BETA", ciks=["200"]), 300_000_000_000),
        ]
        cik_ticker_map = {
            "100": ("ALPH", "Alpha"),
            "200": ("BETA", "Beta Corp"),
        }
        results = builder.resolve_entities(hits_with_cap, cik_ticker_map)
        assert mock_resolver.resolve_entity.call_count == 2
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------


class TestPersist:
    """Tests for database persistence phase."""

    def test_persist_creates_new_companies(
        self, builder, sqlite_session_factory
    ) -> None:
        """New CIKs result in new Company rows."""
        resolutions = [
            _make_resolution("ALPHA INC", "100", ticker="ALPH"),
            _make_resolution("BETA CORP", "200", ticker="BETA"),
        ]
        market_caps = {"100": 500_000_000_000, "200": 300_000_000_000}
        scan = date(2025, 12, 15)

        with sqlite_session_factory() as session:
            new, updated, deactivated = builder.persist(
                resolutions, market_caps, scan, session
            )

        assert new == 2
        assert updated == 0
        assert deactivated == 0

        # Verify rows exist
        with sqlite_session_factory() as session:
            companies = session.query(Company).all()
            assert len(companies) == 2

    def test_persist_updates_existing_companies(
        self, builder, sqlite_session_factory
    ) -> None:
        """Existing CIKs get updated market_cap and aliases."""
        # Pre-insert a company
        with sqlite_session_factory() as session:
            session.add(
                Company(
                    id=uuid.uuid4(),
                    ticker="ALPH",
                    name="Alpha Inc",
                    cik="100",
                    market_cap_cents=400_000_000_000,
                    aliases={},
                    is_active=True,
                )
            )
            session.commit()

        resolutions = [
            _make_resolution("ALPHA INC", "100", ticker="ALPH"),
        ]
        market_caps = {"100": 500_000_000_000}
        scan = date(2025, 12, 15)

        with sqlite_session_factory() as session:
            new, updated, deactivated = builder.persist(
                resolutions, market_caps, scan, session
            )

        assert new == 0
        assert updated == 1

        with sqlite_session_factory() as session:
            company = session.query(Company).filter_by(cik="100").one()
            assert company.market_cap_cents == 500_000_000_000

    def test_persist_deactivates_missing_companies(
        self, builder, sqlite_session_factory
    ) -> None:
        """Companies from previous scan not in current scan are deactivated per D-10."""
        # Pre-insert 2 companies
        with sqlite_session_factory() as session:
            session.add_all([
                Company(
                    id=uuid.uuid4(),
                    ticker="ALPH",
                    name="Alpha Inc",
                    cik="100",
                    aliases={},
                    is_active=True,
                ),
                Company(
                    id=uuid.uuid4(),
                    ticker="GONE",
                    name="Gone Corp",
                    cik="999",
                    aliases={},
                    is_active=True,
                ),
            ])
            session.commit()

        # Current scan only has CIK 100
        resolutions = [_make_resolution("ALPHA INC", "100", ticker="ALPH")]
        market_caps = {"100": 500_000_000_000}
        scan = date(2025, 12, 15)

        with sqlite_session_factory() as session:
            new, updated, deactivated = builder.persist(
                resolutions, market_caps, scan, session
            )

        assert deactivated == 1

        with sqlite_session_factory() as session:
            gone = session.query(Company).filter_by(cik="999").one()
            assert gone.is_active is False
            assert "not_in_scan" in gone.deactivation_reason


# ---------------------------------------------------------------------------
# Full build pipeline tests
# ---------------------------------------------------------------------------


class TestBuild:
    """Tests for the full build() pipeline."""

    def test_build_returns_result(self, builder) -> None:
        """build() returns a UniverseBuildResult with expected fields."""
        result = builder.build(scan_date=date(2025, 12, 15))
        assert isinstance(result, UniverseBuildResult)
        assert result.scan_date == date(2025, 12, 15)
        assert result.company_count >= 0

    def test_build_deterministic_output(
        self, builder, mock_efts, mock_edgar, mock_resolver
    ) -> None:
        """Same inputs produce identical output (sort order, counts) per D-06."""
        result1 = builder.build(scan_date=date(2025, 12, 15))
        result2 = builder.build(scan_date=date(2025, 12, 15))
        assert result1.company_count == result2.company_count
        assert result1.scan_date == result2.scan_date

    def test_build_filters_companies(self, builder) -> None:
        """build() excludes companies outside market cap range."""
        result = builder.build(scan_date=date(2025, 12, 15))
        # 3 companies from EFTS, but CIK 300 ($500M) is below min
        assert result.company_count == 2

    def test_build_deactivation_on_rescan(
        self,
        universe_settings,
        app_settings,
        mock_resolver,
        sqlite_session_factory,
    ) -> None:
        """Second build with fewer companies deactivates missing ones per D-10."""
        # First build: 2 companies pass market cap
        mock_efts_1 = MagicMock()
        mock_efts_1.search_filings.return_value = [
            _make_hit("ALPHA INC", ciks=["100"]),
            _make_hit("BETA CORP", ciks=["200"]),
        ]
        mock_edgar_1 = MagicMock()
        mock_edgar_1.get_entity_public_float_batch.return_value = {
            "100": 500_000_000_000,
            "200": 300_000_000_000,
        }
        mock_edgar_1.get_cik_ticker_mapping.return_value = {
            "100": ("ALPH", "Alpha Inc"),
            "200": ("BETA", "Beta Corp"),
        }

        builder1 = UniverseBuilder(
            settings=universe_settings,
            app_settings=app_settings,
            efts_client=mock_efts_1,
            edgar_client=mock_edgar_1,
            entity_resolver=mock_resolver,
            session_factory=sqlite_session_factory,
        )
        result1 = builder1.build(scan_date=date(2025, 12, 15))
        assert result1.company_count == 2
        assert result1.new_count == 2

        # Second build: only 1 company
        mock_efts_2 = MagicMock()
        mock_efts_2.search_filings.return_value = [
            _make_hit("ALPHA INC", ciks=["100"]),
        ]
        mock_edgar_2 = MagicMock()
        mock_edgar_2.get_entity_public_float_batch.return_value = {
            "100": 500_000_000_000,
        }
        mock_edgar_2.get_cik_ticker_mapping.return_value = {
            "100": ("ALPH", "Alpha Inc"),
        }

        builder2 = UniverseBuilder(
            settings=universe_settings,
            app_settings=app_settings,
            efts_client=mock_efts_2,
            edgar_client=mock_edgar_2,
            entity_resolver=mock_resolver,
            session_factory=sqlite_session_factory,
        )
        result2 = builder2.build(scan_date=date(2025, 12, 20))
        assert result2.deactivated_count == 1
        assert result2.company_count == 1


# ---------------------------------------------------------------------------
# build_universe convenience function
# ---------------------------------------------------------------------------


class TestBuildUniverseConvenience:
    """Tests for the build_universe top-level function."""

    def test_build_universe_is_importable(self) -> None:
        """build_universe is importable from the module."""
        assert callable(build_universe)
