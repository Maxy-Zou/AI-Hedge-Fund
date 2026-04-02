"""Universe construction orchestrator.

Coordinates EFTS search, market cap filtering, entity resolution,
and Company table persistence to build and maintain the target universe
of mid-cap companies claiming AI capabilities.

Usage::

    from ai_washer.universe.builder import build_universe
    result = build_universe()
    print(f"Found {result.company_count} companies")
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai_washer.config import AppSettings, UniverseSettings, load_app_settings
from ai_washer.db.models import Company
from ai_washer.db.session import create_engine_from_settings, get_session_factory
from ai_washer.entity.resolver import EntityResolver
from ai_washer.entity.types import EntityResolutionResult
from ai_washer.ingestion.edgar_client import EdgarFactsClient, strip_cik
from ai_washer.ingestion.efts_client import EFTSClient
from ai_washer.universe.filters import deduplicate_by_cik, filter_by_market_cap
from ai_washer.universe.types import EFTSHit, MarketCapRange

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class UniverseBuildResult:
    """Immutable result of a universe build operation."""

    scan_date: date
    company_count: int
    new_count: int
    updated_count: int
    deactivated_count: int
    skipped_no_market_cap: int


class UniverseBuilder:
    """Orchestrates the full universe build pipeline.

    Pipeline stages:
    1. EFTS keyword search for AI-claiming companies (per keyword, not combined)
    2. CIK deduplication with deterministic sorting
    3. Market cap filtering via EntityPublicFloat (batch)
    4. Entity resolution for cross-source aliases
    5. Persist to Company table (upsert by CIK)
    6. Soft-remove companies no longer in scan (D-10)

    All dependencies accept injection for testability. When not injected,
    clients are constructed from settings.

    Args:
        settings: Universe configuration (thresholds, keywords, etc.).
        app_settings: Application settings (DB URL, EDGAR identity).
        session_factory: Optional SQLAlchemy session factory.
        efts_client: Optional injected EFTSClient (for testing).
        edgar_client: Optional injected EdgarFactsClient (for testing).
        entity_resolver: Optional injected EntityResolver (for testing).
    """

    def __init__(
        self,
        settings: UniverseSettings,
        app_settings: AppSettings,
        session_factory: sessionmaker[Session] | None = None,
        efts_client: EFTSClient | None = None,
        edgar_client: EdgarFactsClient | None = None,
        entity_resolver: EntityResolver | None = None,
    ) -> None:
        self._settings = settings
        self._app_settings = app_settings

        # Dependency injection or default construction
        self._efts_client = efts_client or EFTSClient(
            edgar_identity=app_settings.edgar_identity,
            page_size=settings.efts_page_size,
        )
        self._edgar_client = edgar_client or EdgarFactsClient(
            edgar_identity=app_settings.edgar_identity,
        )
        self._entity_resolver = entity_resolver or EntityResolver(
            threshold=settings.fuzzy_match_threshold,
        )

        if session_factory is not None:
            self._session_factory = session_factory
        else:
            engine = create_engine_from_settings(app_settings)
            self._session_factory = get_session_factory(engine)

    def scan(self, scan_date: date | None = None) -> list[EFTSHit]:
        """Stage 1-2: Search EFTS for each keyword and deduplicate.

        Searches each keyword separately (not combined) to avoid
        the EFTS 10K result cap per Pitfall 1. Keywords are wrapped
        in double quotes for exact phrase matching.

        Uses a 12-month lookback window from scan_date per D-05.

        Args:
            scan_date: Reference date for the search window. Defaults to today.

        Returns:
            Deduplicated EFTS hits sorted by CIK for determinism.
        """
        if scan_date is None:
            scan_date = date.today()

        date_start = scan_date - timedelta(days=365)
        start_str = date_start.isoformat()
        end_str = scan_date.isoformat()

        all_hits: list[EFTSHit] = []

        for keyword in self._settings.ai_keywords:
            quoted_query = f'"{keyword}"'
            hits = self._efts_client.search_filings(
                query=quoted_query,
                forms="10-K",
                date_start=start_str,
                date_end=end_str,
            )
            all_hits.extend(hits)
            logger.info(
                "efts_keyword_search_done",
                keyword=keyword,
                hits=len(hits),
            )

        unique = deduplicate_by_cik(all_hits)
        logger.info(
            "scan_complete",
            keywords=len(self._settings.ai_keywords),
            total_raw=len(all_hits),
            unique=len(unique),
        )
        return unique

    def filter_market_cap(
        self, hits: list[EFTSHit]
    ) -> list[tuple[EFTSHit, int]]:
        """Stage 3: Filter hits by EntityPublicFloat market cap range.

        Batch-fetches EntityPublicFloat for all CIKs, then filters
        using the configured MarketCapRange thresholds.

        Args:
            hits: Deduplicated EFTS search results.

        Returns:
            List of (hit, public_float_cents) tuples for hits within range.
        """
        cap_range = MarketCapRange(
            min_cents=self._settings.market_cap_min_cents,
            max_cents=self._settings.market_cap_max_cents,
        )

        ciks = [strip_cik(h.ciks[0]) for h in hits if h.ciks]
        float_map = self._edgar_client.get_entity_public_float_batch(ciks)

        results: list[tuple[EFTSHit, int]] = []
        skipped_no_data = 0
        skipped_out_of_range = 0

        for hit in hits:
            if not hit.ciks:
                continue
            cik = strip_cik(hit.ciks[0])
            public_float = float_map.get(cik)

            if public_float is None:
                skipped_no_data += 1
                continue

            if filter_by_market_cap(public_float, cap_range):
                results.append((hit, public_float))
            else:
                skipped_out_of_range += 1

        logger.info(
            "market_cap_filter_done",
            input=len(hits),
            passed=len(results),
            skipped_no_data=skipped_no_data,
            skipped_out_of_range=skipped_out_of_range,
        )
        return results

    def resolve_entities(
        self,
        hits_with_cap: list[tuple[EFTSHit, int]],
        cik_ticker_map: dict[str, tuple[str, str]],
    ) -> list[EntityResolutionResult]:
        """Stage 4: Resolve entity identities across data sources.

        Maps each EFTS hit to a canonical identity using the entity
        resolver, populating aliases for cross-source matching.

        Args:
            hits_with_cap: Filtered (hit, public_float_cents) tuples.
            cik_ticker_map: CIK-to-(ticker, title) mapping from SEC.

        Returns:
            List of EntityResolutionResult with populated aliases.
        """
        results: list[EntityResolutionResult] = []

        for hit, _public_float in hits_with_cap:
            cik = strip_cik(hit.ciks[0])
            ticker_info = cik_ticker_map.get(cik)
            ticker = ticker_info[0] if ticker_info else None

            result = self._entity_resolver.resolve_entity(
                sec_name=hit.entity_name,
                cik=cik,
                ticker=ticker,
            )
            results.append(result)

        logger.info(
            "entity_resolution_done",
            resolved=len(results),
        )
        return results

    def persist(
        self,
        results: list[EntityResolutionResult],
        market_caps: dict[str, int],
        scan_date: date,
        session: Session,
    ) -> tuple[int, int, int]:
        """Stage 5-6: Persist resolved companies and soft-remove missing.

        Creates new Company rows for new CIKs, updates existing ones,
        and marks companies from previous scans that are no longer
        in the current scan as is_active=False per D-10.

        Args:
            results: Resolved entity results to persist.
            market_caps: CIK-to-public_float_cents mapping.
            scan_date: Date of this scan (used in deactivation reason).
            session: Active SQLAlchemy session.

        Returns:
            Tuple of (new_count, updated_count, deactivated_count).
        """
        new_count = 0
        updated_count = 0
        deactivated_count = 0

        current_scan_ciks: set[str] = set()

        for result in results:
            cik = result.matched_cik
            current_scan_ciks.add(cik)

            existing = session.execute(
                select(Company).where(Company.cik == cik)
            ).scalar_one_or_none()

            if existing is None:
                ticker = result.ticker or f"CIK{cik}"
                company = Company(
                    ticker=ticker,
                    name=result.sec_name,
                    cik=cik,
                    market_cap_cents=market_caps.get(cik),
                    aliases=result.resolved_aliases.model_dump(mode="json"),
                    is_active=True,
                )
                session.add(company)
                new_count += 1
            else:
                existing.market_cap_cents = market_caps.get(cik)
                existing.aliases = result.resolved_aliases.model_dump(
                    mode="json"
                )
                existing.is_active = True
                existing.deactivation_reason = None
                updated_count += 1

        # Soft-remove previously active companies not in current scan (D-10)
        active_companies = (
            session.execute(
                select(Company).where(Company.is_active == True)  # noqa: E712
            )
            .scalars()
            .all()
        )

        for company in active_companies:
            if company.cik not in current_scan_ciks:
                company.is_active = False
                company.deactivation_reason = f"not_in_scan_{scan_date}"
                deactivated_count += 1

        session.commit()

        logger.info(
            "persist_complete",
            new=new_count,
            updated=updated_count,
            deactivated=deactivated_count,
        )
        return new_count, updated_count, deactivated_count

    def build(self, scan_date: date | None = None) -> UniverseBuildResult:
        """Execute the full universe build pipeline.

        Runs all stages in sequence: scan -> deduplicate -> market cap
        filter -> entity resolution -> persist -> soft-remove.

        Args:
            scan_date: Date to record for this scan. Defaults to today.

        Returns:
            UniverseBuildResult with counts of new, updated, deactivated.
        """
        if scan_date is None:
            scan_date = date.today()

        # Stage 1-2: Search and deduplicate
        hits = self.scan(scan_date)

        # Stage 3: Market cap filter
        filtered = self.filter_market_cap(hits)
        skipped_no_cap = len(hits) - len(filtered)

        # Stage 4: Entity resolution
        cik_ticker_map = self._edgar_client.get_cik_ticker_mapping()
        results = self.resolve_entities(filtered, cik_ticker_map)

        # Build market cap lookup for persist
        market_caps = {
            strip_cik(h.ciks[0]): cap for h, cap in filtered
        }

        # Stage 5-6: Persist and soft-remove
        with self._session_factory() as session:
            new_count, updated_count, deactivated_count = self.persist(
                results, market_caps, scan_date, session
            )

        company_count = len(results)

        logger.info(
            "universe_build_complete",
            scan_date=str(scan_date),
            company_count=company_count,
            new=new_count,
            updated=updated_count,
            deactivated=deactivated_count,
            skipped_no_cap=skipped_no_cap,
        )

        return UniverseBuildResult(
            scan_date=scan_date,
            company_count=company_count,
            new_count=new_count,
            updated_count=updated_count,
            deactivated_count=deactivated_count,
            skipped_no_market_cap=skipped_no_cap,
        )


def build_universe(
    settings: UniverseSettings | None = None,
    app_settings: AppSettings | None = None,
    scan_date: date | None = None,
) -> UniverseBuildResult:
    """Convenience function: build universe with default settings.

    Args:
        settings: Optional UniverseSettings. Defaults to UniverseSettings().
        app_settings: Optional AppSettings. Defaults to load_app_settings().
        scan_date: Optional scan date. Defaults to today.

    Returns:
        UniverseBuildResult with scan summary.
    """
    if settings is None:
        settings = UniverseSettings()
    if app_settings is None:
        app_settings = load_app_settings()

    builder = UniverseBuilder(settings=settings, app_settings=app_settings)
    return builder.build(scan_date=scan_date)
