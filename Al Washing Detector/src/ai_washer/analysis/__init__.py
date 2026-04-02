"""Analysis package: shared building blocks for SEC and compute scoring engines.

Exports type contracts, keyword lexicon with section-weighted counting,
growth rate utilities, and sigmoid score normalization.
"""

from ai_washer.analysis.types import (
    FilingForScoring,
    GrowthRateResult,
    KeywordFrequencyResult,
    KeywordLexicon,
    SectionKeywordCounts,
    SignalResult,
)
from ai_washer.analysis.keywords import (
    CLOUD_COMPUTE_KEYWORDS,
    DEFAULT_SECTION_WEIGHTS,
    EARNINGS_SECTION_WEIGHTS,
    EARNINGS_SUBSTANTIVE_TERMS,
    EARNINGS_VAGUE_TERMS,
    SUBSTANTIVE_TERMS,
    VAGUE_BUZZWORDS,
    compile_lexicon,
    compute_section_weighted_frequency,
    count_keywords_in_text,
)
from ai_washer.analysis.finbert_analyzer import (
    FinBERTAnalyzer,
    SentimentResult,
    chunk_text_for_bert,
)
from ai_washer.analysis.growth import build_yearly_series, compute_cagr
from ai_washer.analysis.normalization import sigmoid_normalize
from ai_washer.analysis.sec_filing_scorer import (
    compute_filing_mismatch_ratio,
    compute_keyword_counts_by_year,
    compute_sec_filing_score,
)
from ai_washer.analysis.compute_spending_scorer import (
    compute_capex_keyword_gap,
    compute_compute_spending_score,
    count_cloud_mentions_by_year,
)
from ai_washer.analysis.github_activity_scorer import compute_github_activity_score
from ai_washer.analysis.patent_gap_scorer import compute_patent_gap_score
from ai_washer.analysis.composite_scorer import (
    ALL_SIGNAL_TYPES,
    SIGNAL_TYPE_TO_WEIGHT_KEY,
    CompositeResult,
    classify_risk_band,
    compute_composite_score,
)
from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator

__all__ = [
    # Types
    "FilingForScoring",
    "GrowthRateResult",
    "KeywordFrequencyResult",
    "KeywordLexicon",
    "SectionKeywordCounts",
    "SignalResult",
    # Keywords
    "CLOUD_COMPUTE_KEYWORDS",
    "DEFAULT_SECTION_WEIGHTS",
    "EARNINGS_SECTION_WEIGHTS",
    "EARNINGS_SUBSTANTIVE_TERMS",
    "EARNINGS_VAGUE_TERMS",
    "SUBSTANTIVE_TERMS",
    "VAGUE_BUZZWORDS",
    "compile_lexicon",
    "compute_section_weighted_frequency",
    "count_keywords_in_text",
    # Growth
    "build_yearly_series",
    "compute_cagr",
    # Normalization
    "sigmoid_normalize",
    # SEC Filing Scorer
    "compute_filing_mismatch_ratio",
    "compute_keyword_counts_by_year",
    "compute_sec_filing_score",
    # Compute spending scorer
    "compute_capex_keyword_gap",
    "compute_compute_spending_score",
    "count_cloud_mentions_by_year",
    # Patent gap scorer
    "compute_patent_gap_score",
    # GitHub activity scorer
    "compute_github_activity_score",
    # FinBERT analyzer
    "FinBERTAnalyzer",
    "SentimentResult",
    "chunk_text_for_bert",
    # Composite scorer
    "ALL_SIGNAL_TYPES",
    "SIGNAL_TYPE_TO_WEIGHT_KEY",
    "CompositeResult",
    "classify_risk_band",
    "compute_composite_score",
    # Scoring orchestrator
    "ScoringOrchestrator",
]
