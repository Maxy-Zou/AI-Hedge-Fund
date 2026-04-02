"""Pydantic type contracts for USPTO patent collection.

Defines schemas for patent data from the PatentSearch API, frozen scoring inputs,
and collection results. These types form the contract between the ingestion layer
(patent client/collector) and the scoring layer (patent gap scorer).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CPC_AI_PREFIXES: tuple[str, ...] = ("G06N", "G06F18")
"""CPC code prefixes that indicate AI-related patents.

G06N: Computing arrangements based on specific computational models
      (neural networks, genetic algorithms, machine learning)
G06F18: Pattern recognition (classification, clustering)

Used as `_begins` filter values in the PatentSearch API.
"""

PATENT_SIGNAL_VERSION: str = "0.5.0"
"""Signal version for audit traceability, matching Phase 5 numbering convention."""


# ---------------------------------------------------------------------------
# PatentRecord -- API response schema
# ---------------------------------------------------------------------------


class PatentRecord(BaseModel):
    """Pydantic schema for a single patent from the PatentSearch API response.

    Validates API response data at the ingestion boundary per project constraints.
    Maps to the ``patents`` response array from the PatentSearch ``/patent/``
    endpoint.
    """

    patent_id: str = Field(min_length=1)
    """Patent identifier, e.g. ``US-12345678-A1``."""

    patent_title: str = Field(min_length=1)
    """Title of the granted patent."""

    patent_date: date
    """Grant date of the patent."""

    assignee_organization: str
    """Organization name of the patent assignee."""

    cpc_codes: list[str] = Field(default_factory=list)
    """CPC classification codes, e.g. ``["G06N3/08", "G06F18/24"]``."""


# ---------------------------------------------------------------------------
# PatentForScoring -- frozen scoring input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatentForScoring:
    """Immutable input for patent gap scoring functions.

    Follows the FilingForScoring frozen dataclass pattern from analysis/types.py.
    Uses tuple for cpc_codes (not list) to guarantee immutability.
    """

    patent_id: str
    grant_date: date
    cpc_codes: tuple[str, ...]
    assignee_organization: str


# ---------------------------------------------------------------------------
# PatentCollectionResult -- operational tracking
# ---------------------------------------------------------------------------


class PatentCollectionResult(BaseModel):
    """Result of collecting patents for one company.

    Tracks counts of patents collected, skipped, and errors encountered.
    Mirrors CollectionResult from ingestion/types.py.
    """

    company_cik: str
    patent_count: int = 0
    skipped_count: int = 0
    errors: list[str] = Field(default_factory=list)
