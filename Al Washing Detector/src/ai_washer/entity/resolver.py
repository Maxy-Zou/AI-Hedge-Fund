"""Entity resolution engine with fuzzy matching.

Maps SEC company names to aliases across data sources (patent assignees,
GitHub orgs, job posting employers) using rapidfuzz for fuzzy string
matching and the normalizer for preprocessing.
"""

from __future__ import annotations

from datetime import date
from statistics import mean
from typing import TYPE_CHECKING

import structlog
from rapidfuzz import fuzz, process

from ai_washer.entity.normalizer import normalize_company_name
from ai_washer.entity.types import (
    AliasesSchema,
    EntityResolutionResult,
    ResolutionMetadata,
    ResolutionMethod,
)

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# Sources that use fuzzy matching (list-valued in AliasesSchema)
_FUZZY_SOURCES: tuple[str, ...] = ("patent_assignee", "employer_names")


class EntityResolver:
    """Resolves SEC company identities across data sources.

    Uses rapidfuzz token_sort_ratio for fuzzy matching of company names
    from different data sources. Configurable thresholds control match
    sensitivity and review flagging.

    Args:
        threshold: Minimum fuzzy match score (0-100) to accept a match.
        high_confidence_threshold: Score at or above which needs_review is False.
    """

    def __init__(
        self,
        threshold: int = 85,
        high_confidence_threshold: int = 95,
    ) -> None:
        if threshold < 50 or threshold > 100:
            msg = f"threshold must be between 50 and 100 (got {threshold})"
            raise ValueError(msg)
        if high_confidence_threshold < 50 or high_confidence_threshold > 100:
            msg = f"high_confidence_threshold must be between 50 and 100 (got {high_confidence_threshold})"
            raise ValueError(msg)
        self.threshold = threshold
        self.high_confidence_threshold = high_confidence_threshold

    def resolve_entity(
        self,
        sec_name: str,
        cik: str,
        candidates: dict[str, list[str]] | None = None,
        ticker: str | None = None,
    ) -> EntityResolutionResult:
        """Resolve a single SEC entity against candidate names from other sources.

        Args:
            sec_name: Company name as it appears in SEC filings.
            cik: SEC Central Index Key.
            candidates: Dict mapping source names to candidate name lists.
                Supported keys: "patent_assignee", "employer_names", "github_org".
            ticker: Optional stock ticker symbol.

        Returns:
            EntityResolutionResult with resolved aliases and metadata.
        """
        normalized_sec = normalize_company_name(sec_name)
        candidates = candidates or {}

        # Initialize aliases with CIK always set
        patent_assignee: list[str] = []
        employer_names: list[str] = []
        github_org: str | None = None

        match_scores: list[float] = []
        has_low_confidence_match = False

        # Fuzzy match for list-valued sources
        for source in _FUZZY_SOURCES:
            source_candidates = candidates.get(source, [])
            if not source_candidates:
                continue

            matched_name, score = _fuzzy_match_best(
                normalized_sec,
                source_candidates,
                self.threshold,
            )
            if matched_name is not None and score is not None:
                if source == "patent_assignee":
                    patent_assignee.append(matched_name)
                elif source == "employer_names":
                    employer_names.append(matched_name)

                match_scores.append(score)
                if score < self.high_confidence_threshold:
                    has_low_confidence_match = True

                logger.debug(
                    "fuzzy_match_found",
                    sec_name=sec_name,
                    source=source,
                    matched=matched_name,
                    score=score,
                )

        # GitHub org: exact match after lowering (short slugs, not fuzzy-friendly)
        github_candidates = candidates.get("github_org", [])
        if github_candidates:
            github_org = _exact_match_github_org(normalized_sec, github_candidates)
            if github_org is not None:
                # Exact match is always high confidence
                match_scores.append(100.0)

        # Calculate overall confidence
        overall_confidence = mean(match_scores) / 100.0 if match_scores else 0.0

        # Determine needs_review flag
        needs_review = has_low_confidence_match if match_scores else False

        metadata = ResolutionMetadata(
            resolved_at=date.today(),
            method=ResolutionMethod.AUTOMATED_FUZZY,
            confidence=round(overall_confidence, 4),
            needs_review=needs_review,
        )

        aliases = AliasesSchema(
            cik=cik,
            patent_assignee=patent_assignee,
            github_org=github_org,
            employer_names=employer_names,
            resolution_metadata=metadata,
        )

        return EntityResolutionResult(
            sec_name=sec_name,
            matched_cik=cik,
            ticker=ticker,
            resolved_aliases=aliases,
        )

    def resolve_batch(
        self,
        entities: list[tuple[str, str, str | None]],
        candidates: dict[str, list[str]] | None = None,
    ) -> list[EntityResolutionResult]:
        """Resolve a batch of SEC entities.

        Args:
            entities: List of (sec_name, cik, ticker) tuples.
            candidates: Shared candidate dict for all entities.

        Returns:
            List of EntityResolutionResult in same order as input.
        """
        results: list[EntityResolutionResult] = []
        total = len(entities)

        for i, (sec_name, cik, ticker) in enumerate(entities):
            result = self.resolve_entity(
                sec_name=sec_name,
                cik=cik,
                candidates=candidates,
                ticker=ticker,
            )
            results.append(result)

            if (i + 1) % 50 == 0:
                logger.info(
                    "batch_progress",
                    completed=i + 1,
                    total=total,
                )

        if total > 0:
            logger.info(
                "batch_complete",
                total=total,
            )

        return results


def resolve_entity(
    sec_name: str,
    cik: str,
    candidates: dict[str, list[str]] | None = None,
    threshold: int = 85,
) -> EntityResolutionResult:
    """Convenience function: resolve a single entity with default settings.

    Creates an EntityResolver with the given threshold and resolves one entity.

    Args:
        sec_name: Company name from SEC filings.
        cik: SEC Central Index Key.
        candidates: Optional dict mapping source names to candidate name lists.
        threshold: Minimum fuzzy match score (0-100).

    Returns:
        EntityResolutionResult with resolved aliases.
    """
    resolver = EntityResolver(threshold=threshold)
    return resolver.resolve_entity(sec_name, cik, candidates)


def _fuzzy_match_best(
    normalized_query: str,
    raw_candidates: list[str],
    threshold: int,
) -> tuple[str | None, float | None]:
    """Find the best fuzzy match among candidates.

    Normalizes each candidate for comparison but returns the original
    (unnormalized) candidate name on match.

    Args:
        normalized_query: Already-normalized SEC company name.
        raw_candidates: Candidate names in their original form.
        threshold: Minimum score to accept.

    Returns:
        Tuple of (original_candidate_name, score) or (None, None).
    """
    if not raw_candidates:
        return None, None

    # Build mapping: normalized -> original (preserving first occurrence)
    norm_to_original: dict[str, str] = {}
    normalized_candidates: list[str] = []
    for candidate in raw_candidates:
        normed = normalize_company_name(candidate)
        if normed not in norm_to_original:
            norm_to_original[normed] = candidate
            normalized_candidates.append(normed)

    result = process.extractOne(
        normalized_query,
        normalized_candidates,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold,
    )

    if result is None:
        return None, None

    matched_normalized, score, _index = result
    original_name = norm_to_original[matched_normalized]
    return original_name, score


def _exact_match_github_org(
    normalized_sec_name: str,
    github_candidates: list[str],
) -> str | None:
    """Find an exact match for a GitHub org slug.

    GitHub orgs are short slugs (e.g., "alphabet", "google") so fuzzy
    matching would produce too many false positives. Instead, compare
    lowered/stripped versions against the first word of the SEC name.

    Args:
        normalized_sec_name: Already-normalized SEC company name.
        github_candidates: GitHub org slug candidates.

    Returns:
        The matched GitHub org slug, or None.
    """
    # Extract first word of SEC name for matching against short slugs
    sec_lower = normalized_sec_name.lower().strip()
    sec_words = sec_lower.split()
    if not sec_words:
        return None

    sec_first_word = sec_words[0]

    for candidate in github_candidates:
        candidate_lower = candidate.lower().strip()
        # Match if candidate equals the full normalized name or the first word
        if candidate_lower == sec_lower or candidate_lower == sec_first_word:
            return candidate

    return None
