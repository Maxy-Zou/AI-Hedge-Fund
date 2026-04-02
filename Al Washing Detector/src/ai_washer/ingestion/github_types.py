"""Pydantic type contracts for GitHub repository collection.

Defines schemas for GitHub org/repo data, frozen scoring inputs,
and collection results. These types form the contract between the ingestion
layer (github client/collector) and the scoring layer (github activity scorer).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_SIGNAL_VERSION: str = "0.6.0"
"""Signal version for audit traceability, matching Phase 6 numbering convention."""

ML_FRAMEWORK_PATTERNS: dict[str, list[str]] = {
    "tensorflow": ["tensorflow", "tensorflow-gpu", "tf-nightly", "keras"],
    "pytorch": ["torch", "torchvision", "torchaudio", "pytorch-lightning"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "jax": ["jax", "jaxlib", "flax"],
    "huggingface": ["transformers", "datasets", "tokenizers"],
    "xgboost": ["xgboost"],
    "lightgbm": ["lightgbm"],
}
"""Mapping of ML framework families to their PyPI/import names.

Used to detect ML framework usage in repository dependency files
(requirements.txt, setup.py, pyproject.toml, etc.).
"""

ML_LANGUAGES: tuple[str, ...] = (
    "Python",
    "R",
    "Julia",
    "C++",
    "Rust",
    "Jupyter Notebook",
)
"""Programming languages commonly used for ML/AI development.

Domain constants -- not user-configurable. Used to calculate ML language
ratio from GitHub language bytes breakdown.
"""


# ---------------------------------------------------------------------------
# GitHubRepoRecord -- API response schema
# ---------------------------------------------------------------------------


class GitHubRepoRecord(BaseModel):
    """Pydantic schema for a single GitHub repository.

    Validates GitHub API response data at the ingestion boundary.
    Maps to fields from the GitHub REST API ``/repos`` and ``/orgs/{org}/repos``
    endpoints.
    """

    repo_full_name: str = Field(min_length=1)
    """Full repository name, e.g. ``org/repo-name``."""

    repo_name: str
    """Short repository name without the org prefix."""

    primary_language: str | None
    """Primary language as reported by GitHub (may be None for empty repos)."""

    language_bytes: dict[str, int] = Field(default_factory=dict)
    """Language breakdown in bytes from the GitHub Languages API."""

    pushed_at: datetime | None
    """Last push timestamp (may be None for brand-new repos)."""

    is_fork: bool
    """Whether this repo is a fork of another repository."""

    is_archived: bool
    """Whether this repo is archived (read-only)."""

    stargazers_count: int = Field(ge=0)
    """Number of stars on the repository."""

    ml_frameworks: list[str] = Field(default_factory=list)
    """ML framework families detected in this repo's dependencies."""


# ---------------------------------------------------------------------------
# GitHubOrgSnapshot -- aggregated org-level data
# ---------------------------------------------------------------------------


class GitHubOrgSnapshot(BaseModel):
    """Aggregated snapshot of a GitHub organization's ML activity.

    Computed from individual GitHubRepoRecords during collection.
    Used as input to the GitHub activity scorer.
    """

    repo_count: int
    """Total number of public repositories in the org."""

    total_ml_language_bytes: int
    """Sum of language bytes for ML_LANGUAGES across all repos."""

    total_language_bytes: int
    """Sum of all language bytes across all repos."""

    ml_language_ratio: float
    """Ratio of ML language bytes to total language bytes (0.0 to 1.0)."""

    days_since_last_push: int | None
    """Days since the most recent push across all repos (None if no pushes)."""

    ml_frameworks_found: list[str] = Field(default_factory=list)
    """Unique ML framework families detected across all repos."""

    repos: list[GitHubRepoRecord] = Field(default_factory=list)
    """Individual repo records included in this snapshot."""


# ---------------------------------------------------------------------------
# GitHubCollectionResult -- operational tracking
# ---------------------------------------------------------------------------


class GitHubCollectionResult(BaseModel):
    """Result of collecting GitHub data for one company.

    Tracks counts of repos collected, skipped, and errors encountered.
    Mirrors PatentCollectionResult from ingestion/patent_types.py.
    """

    company_cik: str
    repo_count: int = 0
    skipped_count: int = 0
    errors: list[str] = Field(default_factory=list)
