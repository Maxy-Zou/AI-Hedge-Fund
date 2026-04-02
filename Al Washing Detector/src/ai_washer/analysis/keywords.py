"""Two-tier keyword lexicon and section-weighted counting logic.

Provides:
- VAGUE_BUZZWORDS: Tier 1 marketing buzzwords (25+ terms)
- SUBSTANTIVE_TERMS: Tier 2 technical AI terms (25+ terms)
- CLOUD_COMPUTE_KEYWORDS: Cloud/compute partnership indicators (20+ terms)
- compile_lexicon: Pre-compile keywords with word boundary regex
- count_keywords_in_text: Count keyword occurrences in text
- compute_section_weighted_frequency: Section-weighted frequency analysis

Per D-01/D-02 from research: distinguishes vague buzzwords from substantive
AI terms to measure the gap between claims and substance.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ai_washer.analysis.types import KeywordFrequencyResult, SectionKeywordCounts


# ---------------------------------------------------------------------------
# Module-level immutable keyword constants
# ---------------------------------------------------------------------------

VAGUE_BUZZWORDS: tuple[str, ...] = (
    "ai-powered",
    "ai-driven",
    "ai-enabled",
    "ai-first",
    "leveraging ai",
    "leveraging artificial intelligence",
    "leveraging machine learning",
    "powered by ai",
    "powered by artificial intelligence",
    "cutting-edge ai",
    "revolutionary ai",
    "state-of-the-art ai",
    "world-class ai",
    "industry-leading ai",
    "ai capabilities",
    "ai solutions",
    "ai platform",
    "machine learning capabilities",
    "ai-enhanced",
    "ai transformation",
    "ai strategy",
    "ai initiative",
    "intelligent automation",
    "cognitive computing",
    "predictive analytics",
    "smart technology",
    "next-generation ai",
)

SUBSTANTIVE_TERMS: tuple[str, ...] = (
    "neural network",
    "deep learning",
    "transformer model",
    "model training",
    "model inference",
    "inference latency",
    "training data",
    "training pipeline",
    "fine-tuning",
    "gpu cluster",
    "compute infrastructure",
    "natural language processing",
    "computer vision",
    "reinforcement learning",
    "generative adversarial",
    "large language model",
    "embedding",
    "vector database",
    "mlops",
    "model deployment",
    "feature engineering",
    "hyperparameter",
    "gradient descent",
    "backpropagation",
    "convolutional neural",
    "recurrent neural",
    "attention mechanism",
    "tokenization",
)

CLOUD_COMPUTE_KEYWORDS: tuple[str, ...] = (
    "amazon web services",
    "aws",
    "azure",
    "google cloud",
    "gcp",
    "nvidia",
    "gpu",
    "tpu",
    "cloud computing",
    "cloud infrastructure",
    "data center",
    "compute capacity",
    "hyperscaler",
    "cloud partnership",
    "cloud migration",
    "saas",
    "iaas",
    "paas",
    "oracle cloud",
    "ibm cloud",
    "alibaba cloud",
)

DEFAULT_SECTION_WEIGHTS: dict[str, float] = {
    "mda": 0.50,
    "risk_factors": 0.20,
    "business": 0.30,
}

# ---------------------------------------------------------------------------
# Earnings-call-specific keyword constants (Phase 07)
# ---------------------------------------------------------------------------

EARNINGS_VAGUE_TERMS: tuple[str, ...] = (
    "ai-powered",
    "ai-driven",
    "leveraging ai",
    "ai transformation",
    "ai strategy",
    "ai initiatives",
    "ai capabilities",
    "ai solutions",
    "intelligent automation",
    "digital transformation",
    "ai journey",
    "ai roadmap",
    "ai-first",
    "ai opportunity",
    "ai momentum",
    "exciting ai",
    "tremendous ai",
)

EARNINGS_SUBSTANTIVE_TERMS: tuple[str, ...] = (
    "deployed transformer model",
    "trained on",
    "inference latency",
    "gpu cluster",
    "model accuracy",
    "f1 score",
    "training pipeline",
    "feature engineering",
    "a/b testing",
    "model serving",
    "ml infrastructure",
    "data pipeline",
    "model retraining",
    "production model",
    "mlops",
    "fine-tuned",
    "embedding model",
    "vector search",
)

EARNINGS_SECTION_WEIGHTS: dict[str, float] = {
    "prepared_remarks": 0.60,
    "qa": 0.40,
}

# Minimum section text length for scoring (per Phase 3 500-char rule)
_MIN_SECTION_LENGTH = 500


@dataclass(frozen=True)
class KeywordMatch:
    """Single keyword match result. Frozen for immutability."""

    keyword: str
    tier: str
    count: int


def compile_lexicon(
    vague: Sequence[str],
    substantive: Sequence[str],
) -> list[tuple[re.Pattern[str], str, str]]:
    """Pre-compile all keywords with word boundary regex.

    Returns list of (compiled_pattern, keyword_str, tier_str) tuples.
    Per Pitfall 3: word boundaries prevent "AI" matching inside "FAIR", "MAINTAIN".

    Args:
        vague: Tier 1 buzzword terms.
        substantive: Tier 2 technical terms.

    Returns:
        List of (pattern, keyword, tier) tuples ready for matching.
    """
    result: list[tuple[re.Pattern[str], str, str]] = []
    for keyword in vague:
        escaped = re.escape(keyword)
        pattern = re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)
        result.append((pattern, keyword, "vague"))
    for keyword in substantive:
        escaped = re.escape(keyword)
        pattern = re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)
        result.append((pattern, keyword, "substantive"))
    return result


def count_keywords_in_text(
    text: str,
    patterns: list[tuple[re.Pattern[str], str, str]],
) -> list[KeywordMatch]:
    """Count occurrences of each keyword pattern in text.

    Args:
        text: The text to search.
        patterns: Pre-compiled patterns from compile_lexicon.

    Returns:
        List of KeywordMatch with count > 0. Empty list if no matches.
    """
    if not text:
        return []

    lowered = text.lower()
    matches: list[KeywordMatch] = []
    for pattern, keyword, tier in patterns:
        count = len(pattern.findall(lowered))
        if count > 0:
            matches.append(KeywordMatch(keyword=keyword, tier=tier, count=count))
    return matches


def compute_section_weighted_frequency(
    sections: dict[str, str | None],
    patterns: list[tuple[re.Pattern[str], str, str]],
    section_weights: dict[str, float] | None = None,
) -> KeywordFrequencyResult:
    """Compute section-weighted keyword frequency across filing sections.

    For each section key in section_weights:
    - If text is None or len < 500 chars, mark as missing and skip
    - Otherwise count keywords and multiply by section weight
    - Renormalize remaining weights to sum to 1.0

    Args:
        sections: Mapping of section name to text content. Values may be None.
        patterns: Pre-compiled patterns from compile_lexicon.
        section_weights: Optional custom weights. Defaults to DEFAULT_SECTION_WEIGHTS.

    Returns:
        KeywordFrequencyResult with per-section, per-tier breakdowns.
    """
    weights = section_weights if section_weights is not None else DEFAULT_SECTION_WEIGHTS

    by_section: dict[str, SectionKeywordCounts] = {}
    sections_available: list[str] = []
    sections_missing: list[str] = []
    total_vague = 0
    total_substantive = 0

    # Determine which sections are available vs missing
    for section_name in weights:
        text = sections.get(section_name)
        if text is None or len(text) < _MIN_SECTION_LENGTH:
            sections_missing.append(section_name)
            continue
        sections_available.append(section_name)

    # Calculate renormalized weights for available sections
    available_weight_sum = sum(weights[s] for s in sections_available)

    # Compute weighted frequency
    total_weighted_count = 0.0
    for section_name in sections_available:
        text = sections[section_name]
        # text is guaranteed non-None by the availability check above
        assert text is not None
        matches = count_keywords_in_text(text, patterns)

        vague_count = sum(m.count for m in matches if m.tier == "vague")
        substantive_count = sum(m.count for m in matches if m.tier == "substantive")
        section_total = vague_count + substantive_count

        by_section[section_name] = SectionKeywordCounts(
            vague_count=vague_count,
            substantive_count=substantive_count,
            total=section_total,
        )

        total_vague += vague_count
        total_substantive += substantive_count

        # Renormalize weight: section_weight / available_weight_sum
        if available_weight_sum > 0:
            normalized_weight = weights[section_name] / available_weight_sum
            total_weighted_count += section_total * normalized_weight

    by_tier = {"vague": total_vague, "substantive": total_substantive}

    return KeywordFrequencyResult(
        total_weighted_count=total_weighted_count,
        by_section=by_section,
        by_tier=by_tier,
        sections_available=sorted(sections_available),
        sections_missing=sorted(sections_missing),
    )
