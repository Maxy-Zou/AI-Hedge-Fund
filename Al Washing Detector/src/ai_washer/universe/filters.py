"""Market cap filtering and CIK-based deduplication for universe building.

Provides utilities to:
- Filter companies by EntityPublicFloat range (widened per Pitfall 2)
- Deduplicate EFTS search hits by normalized CIK, sorted for determinism (D-06)
"""

from __future__ import annotations

import structlog

from ai_washer.ingestion.edgar_client import strip_cik
from ai_washer.universe.types import EFTSHit, MarketCapRange

logger = structlog.get_logger(__name__)


def filter_by_market_cap(
    public_float_cents: int | None,
    cap_range: MarketCapRange,
) -> bool:
    """Check if EntityPublicFloat falls within the target market cap range.

    Returns True if public_float_cents is within [cap_range.min_cents, cap_range.max_cents]
    inclusive. Returns False if public_float_cents is None (unknown market cap).

    Per D-04: uses EntityPublicFloat as market cap proxy with widened thresholds.

    Args:
        public_float_cents: EntityPublicFloat value in cents, or None if unavailable.
        cap_range: Validated market cap range with min/max bounds.

    Returns:
        True if within range, False otherwise.
    """
    if public_float_cents is None:
        return False
    return cap_range.min_cents <= public_float_cents <= cap_range.max_cents


def deduplicate_by_cik(hits: list[EFTSHit]) -> list[EFTSHit]:
    """Deduplicate EFTS hits by CIK, keeping first occurrence per CIK.

    Per D-06: sort by stripped CIK ascending for deterministic output.
    A single company may have multiple 10-K filings in the search window.
    We keep only the first (most recent by file_date if EFTS returns newest first).

    CIK comparison normalizes format by stripping leading zeros before comparing,
    so "0000012345" and "12345" are treated as the same entity.

    Args:
        hits: Raw EFTS search results, possibly containing duplicates.

    Returns:
        Deduplicated list sorted by first CIK ascending.
    """
    seen_ciks: set[str] = set()
    unique: list[EFTSHit] = []

    for hit in hits:
        for raw_cik in hit.ciks:
            normalized = strip_cik(raw_cik)
            if normalized not in seen_ciks:
                seen_ciks.add(normalized)
                unique.append(hit)
                break  # Only add the hit once even if it has multiple CIKs

    # Sort by first CIK for determinism (D-06)
    unique.sort(key=lambda h: strip_cik(h.ciks[0]) if h.ciks else "")

    logger.info(
        "deduplicated_efts_hits",
        total_input=len(hits),
        unique_output=len(unique),
    )

    return unique
