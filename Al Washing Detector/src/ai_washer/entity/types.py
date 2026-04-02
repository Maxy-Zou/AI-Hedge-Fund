"""Pydantic type contracts for entity resolution.

Defines the schema for Company.aliases JSONB field (per D-02),
resolution metadata, and entity resolution results.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class ResolutionMethod(StrEnum):
    """Method used to resolve a company's identity across data sources."""

    AUTOMATED_FUZZY = "automated_fuzzy"
    MANUAL_SEED = "manual_seed"
    MANUAL_OVERRIDE = "manual_override"


class ResolutionMetadata(BaseModel):
    """Metadata about how and when an entity was resolved.

    Tracks provenance of the resolution for auditing and review.
    """

    resolved_at: date
    method: ResolutionMethod
    confidence: float = Field(ge=0.0, le=1.0)
    needs_review: bool = False


class AliasesSchema(BaseModel):
    """Validates the Company.aliases JSONB structure per D-02.

    Maps a company across data sources: SEC (CIK), USPTO (patent assignee),
    GitHub (org), and job postings (employer names).

    Per D-03: partial resolution is valid -- null fields are acceptable.
    Downstream composite scoring handles missing signals via graceful degradation.
    """

    cik: str | None = None
    patent_assignee: list[str] = Field(default_factory=list)
    github_org: str | None = None
    employer_names: list[str] = Field(default_factory=list)
    resolution_metadata: ResolutionMetadata | None = None


class EntityResolutionResult(BaseModel):
    """Result of resolving a company's identity across data sources.

    Produced by the entity resolver and consumed by the universe builder
    to populate Company.aliases.
    """

    sec_name: str
    matched_cik: str
    ticker: str | None = None
    resolved_aliases: AliasesSchema
