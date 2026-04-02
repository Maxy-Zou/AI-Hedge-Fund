"""Pydantic type contracts for job posting collection.

Defines schemas for job posting data from python-jobspy, role classification
logic, dedup hashing, and collection results. These types form the contract
between the ingestion layer (job client/collector) and the scoring layer
(job mismatch scorer).
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JOB_SIGNAL_VERSION: str = "0.8.0"
"""Signal version for audit traceability, matching Phase 8 numbering convention."""

ENGINEERING_KEYWORDS: tuple[str, ...] = (
    "machine learning engineer",
    "ml engineer",
    "data scientist",
    "deep learning",
    "nlp engineer",
    "computer vision",
    "pytorch",
    "tensorflow",
    "mlops",
    "ml infrastructure",
    "research scientist",
    "applied scientist",
    "ml platform",
    "model training",
    "feature engineering",
)
"""Keywords indicating genuine AI/ML engineering roles.

Used by classify_role to distinguish substantive AI hiring from marketing roles.
"""

MARKETING_KEYWORDS: tuple[str, ...] = (
    "ai strategy",
    "ai-powered",
    "digital transformation",
    "ai evangelist",
    "innovation lead",
    "thought leader",
    "ai product marketing",
    "ai partnership",
    "ai consultant",
    "ai advisor",
)
"""Keywords indicating AI-adjacent marketing or strategy roles.

Used by classify_role to detect roles that reference AI without technical depth.
"""


# ---------------------------------------------------------------------------
# Role classification
# ---------------------------------------------------------------------------


def classify_role(title: str, description: str) -> str:
    """Classify a job posting as engineering, marketing, or ambiguous.

    Counts keyword hits from ENGINEERING_KEYWORDS and MARKETING_KEYWORDS
    in the lowercased combination of title and description. Engineering
    wins ties (more likely to be a real AI role than marketing).

    Args:
        title: Job title text.
        description: Job description text.

    Returns:
        One of ``"engineering"``, ``"marketing"``, or ``"ambiguous"``.
    """
    combined = f"{title} {description}".lower()

    eng_hits = sum(1 for kw in ENGINEERING_KEYWORDS if kw in combined)
    mkt_hits = sum(1 for kw in MARKETING_KEYWORDS if kw in combined)

    if eng_hits == 0 and mkt_hits == 0:
        return "ambiguous"
    if eng_hits >= mkt_hits:
        return "engineering"
    return "marketing"


# ---------------------------------------------------------------------------
# Dedup hashing
# ---------------------------------------------------------------------------


def compute_job_hash(company: str, title: str, location: str) -> str:
    """Compute a deterministic SHA-256 dedup hash for a job posting.

    Case-insensitive and whitespace-trimmed. The hash uniquely identifies
    a job posting by company + title + location to prevent duplicate storage.

    Args:
        company: Company name.
        title: Job title.
        location: Job location.

    Returns:
        64-character lowercase hex digest (SHA-256).
    """
    normalized = (
        f"{company.lower().strip()}"
        f"|{title.lower().strip()}"
        f"|{location.lower().strip()}"
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# JobRecord -- ingestion boundary schema
# ---------------------------------------------------------------------------


class JobRecord(BaseModel):
    """Pydantic schema for a single job posting from python-jobspy.

    Validates job data at the ingestion boundary. Maps to fields returned
    by the jobspy scraper and enriched with role classification and dedup hash.
    """

    title: str = Field(min_length=1)
    """Job title, e.g. ``"ML Engineer"``."""

    company_name_raw: str
    """Company name as returned by the job board (un-normalized)."""

    location: str | None = None
    """Job location string, e.g. ``"Cupertino, CA"``."""

    description: str | None = None
    """Full job description text."""

    job_url: str | None = None
    """URL to the original job posting."""

    source_site: str
    """Job board source, e.g. ``"indeed"``, ``"linkedin"``, ``"glassdoor"``."""

    role_classification: str
    """Result of classify_role: ``"engineering"``, ``"marketing"``, or ``"ambiguous"``."""

    dedup_hash: str = Field(min_length=64, max_length=64)
    """SHA-256 dedup hash from compute_job_hash (64-char hex)."""


# ---------------------------------------------------------------------------
# JobCollectionResult -- operational tracking
# ---------------------------------------------------------------------------


class JobCollectionResult(BaseModel):
    """Result of collecting job postings for one company.

    Tracks counts of jobs found, new inserts, updates, and errors.
    Mirrors PatentCollectionResult / GitHubCollectionResult pattern.
    """

    company_cik: str
    jobs_found: int = 0
    jobs_new: int = 0
    jobs_updated: int = 0
    errors: list[str] = Field(default_factory=list)
