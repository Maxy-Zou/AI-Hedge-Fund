"""Company name normalization for entity resolution.

Strips legal suffixes (Inc, Corp, LLC, etc.), normalizes case,
whitespace, and punctuation so that SEC names can be fuzzy-matched
against patent assignees, GitHub orgs, and job posting employers.
"""

from __future__ import annotations

# Ordered longest-first so " INCORPORATED" matches before " INC".
LEGAL_SUFFIXES: tuple[str, ...] = (
    " INCORPORATED",
    " CORPORATION",
    " COMPANY",
    " LIMITED",
    " CORP",
    " INC",
    " LTD",
    " LLC",
    " PLC",
    " LP",
    " CO",
    " AG",
    " NV",
    " SA",
)


def normalize_company_name(name: str) -> str:
    """Normalize a company name for entity resolution matching.

    Steps:
        1. Strip leading/trailing whitespace
        2. Upper-case
        3. Remove commas and periods
        4. Collapse multiple spaces
        5. Strip trailing legal suffix (longest-match-first)
        6. Guard: if stripping would empty the name, keep original

    Args:
        name: Raw company name (e.g., "Meta Platforms, Inc.")

    Returns:
        Normalized name (e.g., "META PLATFORMS")
    """
    cleaned = name.strip()
    if not cleaned:
        return ""

    # Upper-case for case-insensitive suffix matching
    cleaned = cleaned.upper()

    # Remove commas and periods before suffix matching
    cleaned = cleaned.replace(",", "").replace(".", "")

    # Collapse multiple spaces to single
    cleaned = " ".join(cleaned.split())

    # Strip trailing legal suffix (longest-match-first ordering)
    for suffix in LEGAL_SUFFIXES:
        # Suffix is already stored without periods (e.g., " NV" not " N.V.")
        # and the input has periods stripped, so direct comparison works.
        if cleaned.endswith(suffix):
            candidate = cleaned[: -len(suffix)].strip()
            # Guard: don't reduce the name to empty
            if candidate:
                cleaned = candidate
            break

    # Final whitespace collapse after stripping
    cleaned = " ".join(cleaned.split())

    return cleaned
