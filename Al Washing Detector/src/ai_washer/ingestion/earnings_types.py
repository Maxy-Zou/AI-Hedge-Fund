"""Pydantic type contracts for earnings call transcript collection.

Defines schemas for earnings transcript data, frozen collection results,
and constants. These types form the contract between the ingestion layer
(earnings client/collector) and the scoring layer (earnings vagueness scorer).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EARNINGS_SIGNAL_VERSION: str = "0.7.0"
"""Signal version for audit traceability, matching Phase 7 numbering convention."""


# ---------------------------------------------------------------------------
# TranscriptRecord -- API response schema
# ---------------------------------------------------------------------------


class TranscriptRecord(BaseModel):
    """Pydantic schema for a single earnings call transcript.

    Validates data at the ingestion boundary. Maps to fields from the
    earningscall library or other transcript sources.

    Args:
        ticker: Stock ticker symbol, e.g. ``AAPL``.
        year: Fiscal year of the earnings call.
        quarter: Fiscal quarter (1-4).
        transcript_date: Date of the earnings call (optional).
        text: Full transcript text.
        speakers: Mapping of role to speaker name (optional).
        source: Data source identifier.
    """

    ticker: str = Field(min_length=1)
    """Stock ticker symbol, e.g. ``AAPL``."""

    year: int
    """Fiscal year of the earnings call."""

    quarter: int = Field(ge=1, le=4)
    """Fiscal quarter, constrained to 1-4."""

    transcript_date: date | None = None
    """Date of the earnings call (optional)."""

    text: str = Field(min_length=1)
    """Full transcript text."""

    speakers: dict[str, str] | None = None
    """Mapping of role to speaker name, e.g. ``{"CEO": "Tim Cook"}``."""

    source: str = "earningscall"
    """Data source identifier. Defaults to ``earningscall``."""


# ---------------------------------------------------------------------------
# EarningsCollectionResult -- operational tracking
# ---------------------------------------------------------------------------


class EarningsCollectionResult(BaseModel, frozen=True):
    """Result of collecting earnings transcripts for one company.

    Tracks counts of transcripts collected, skipped, and errors encountered.
    Frozen (immutable) to prevent accidental mutation of operational results.
    Mirrors PatentCollectionResult from ingestion/patent_types.py.
    """

    company_cik: str
    """SEC CIK of the company."""

    transcript_count: int = 0
    """Number of transcripts successfully collected."""

    skipped_count: int = 0
    """Number of transcripts skipped (already exists, empty, etc.)."""

    errors: list[str] = Field(default_factory=list)
    """List of error messages encountered during collection."""
