"""Pydantic type contracts for universe building.

Defines schemas for EFTS API responses and market cap range validation.

Note: The EFTS search-index API (efts.sec.gov/LATEST/search-index) uses different
field names than the EFTS full-text search API (efts.sec.gov/LATEST/search).
The search-index API uses 'adsh' for accession number, 'form' for form type,
and 'period_ending' for period of report. Entity name is derived from display_names.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class EFTSHit(BaseModel):
    """Single EFTS full-text search result from efts.sec.gov.

    Represents one filing match when searching for AI-related terms
    in SEC filings.

    Handles both legacy field names (accession_no, form_type, entity_name)
    and the current search-index API field names (adsh, form, period_ending).
    Entity name is derived from display_names when not present directly.
    """

    accession_no: str
    form_type: str
    file_date: str
    entity_name: str
    ciks: list[str]
    period_of_report: str | None = None
    display_names: list[str] = Field(default_factory=list)

    @classmethod
    def from_search_index(cls, source: dict) -> "EFTSHit":
        """Construct EFTSHit from the search-index API _source dict.

        Maps the current API field names to the canonical EFTSHit schema:
        - adsh -> accession_no
        - form -> form_type
        - period_ending -> period_of_report
        - display_names[0] (text before first '(') -> entity_name

        Args:
            source: The _source dict from a search-index API hit.

        Returns:
            EFTSHit instance with mapped fields.
        """
        display_names: list[str] = source.get("display_names") or []
        # Extract entity name from display_names: "Company Name (TICKER) (CIK ...)"
        if display_names:
            entity_name = display_names[0].split("(")[0].strip()
        else:
            entity_name = "Unknown"

        return cls(
            accession_no=source.get("adsh", ""),
            form_type=source.get("form", ""),
            file_date=source.get("file_date", ""),
            entity_name=entity_name,
            ciks=source.get("ciks") or [],
            period_of_report=source.get("period_ending"),
            display_names=display_names,
        )


class EFTSResponse(BaseModel):
    """Parsed EFTS API response from efts.sec.gov/LATEST/search-index.

    When total_relation is 'gte', the actual total exceeds total_value
    and results are truncated -- pagination is needed.
    """

    total_value: int
    total_relation: str  # "eq" or "gte"
    hits: list[EFTSHit]

    @property
    def is_truncated(self) -> bool:
        """True when EFTS reports more results than returned (needs pagination)."""
        return self.total_relation == "gte"


class MarketCapRange(BaseModel):
    """Valid market cap range in cents for universe filtering.

    Both bounds must be positive and min must be strictly less than max.
    """

    min_cents: int = Field(gt=0)
    max_cents: int = Field(gt=0)

    @model_validator(mode="after")
    def _check_min_lt_max(self) -> MarketCapRange:
        if self.min_cents >= self.max_cents:
            msg = f"min_cents ({self.min_cents}) must be less than max_cents ({self.max_cents})"
            raise ValueError(msg)
        return self
