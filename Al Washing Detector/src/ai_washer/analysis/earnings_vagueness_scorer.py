"""Earnings call vagueness scorer.

Pure-function engine that computes a 0-100 vagueness score combining:
- Buzzword density ratio (70%): proportion of vague vs substantive AI terms
- Sentiment mismatch (30%): positive sentiment with low substance = hype

High score = lots of buzzwords + positive tone (washing signal).
Low score = substantive terms dominate (genuine AI work).

No database access, no side effects. Follows the same pattern as
sec_filing_scorer.py and patent_gap_scorer.py.
"""

from __future__ import annotations

from ai_washer.analysis.finbert_analyzer import SentimentResult
from ai_washer.analysis.keywords import (
    EARNINGS_SUBSTANTIVE_TERMS,
    EARNINGS_VAGUE_TERMS,
    compile_lexicon,
    count_keywords_in_text,
)
from ai_washer.analysis.normalization import sigmoid_normalize
from ai_washer.analysis.types import SignalResult

_EARNINGS_SIGNAL_VERSION = "0.7.0"

_DEFAULT_AI_CLAIM_INTENSITY = 0.5

# Pre-compile earnings lexicon at module level for reuse
_EARNINGS_PATTERNS = compile_lexicon(EARNINGS_VAGUE_TERMS, EARNINGS_SUBSTANTIVE_TERMS)


def compute_earnings_vagueness_score(
    transcript_text: dict[str, str | None],
    sentiment_result: SentimentResult,
    ai_claim_intensity: float | None,
    buzzword_weight: float = 0.70,
    sentiment_weight: float = 0.30,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Compute earnings call vagueness score from transcript text and sentiment.

    Combines buzzword density ratio (default 70%) with sentiment mismatch
    (default 30%) to produce a 0-100 risk score via sigmoid normalization.

    Args:
        transcript_text: Dict with keys like "full_text", "prepared_remarks", "qa".
            Values are str | None per the 07-02 data contract.
        sentiment_result: FinBERT sentiment probabilities for the transcript.
        ai_claim_intensity: Weighted keyword count from SEC filings. None means
            SEC data unavailable (defaults to 0.5). 0.0 means no AI claims
            (returns None -- signal is irrelevant).
        buzzword_weight: Weight for buzzword density component (default 0.70).
        sentiment_weight: Weight for sentiment mismatch component (default 0.30).
        sigmoid_midpoint: Midpoint for sigmoid normalization (default 1.0).
        sigmoid_steepness: Steepness for sigmoid curve (default 2.0).

    Returns:
        SignalResult with signal_type="earnings_vagueness" and score 0-100,
        or None if insufficient data or no AI claims.
    """
    # Handle ai_claim_intensity
    ai_claim_intensity_defaulted = False
    if ai_claim_intensity is None:
        ai_claim_intensity = _DEFAULT_AI_CLAIM_INTENSITY
        ai_claim_intensity_defaulted = True
    elif ai_claim_intensity == 0.0:
        # No AI claims -- earnings vagueness is irrelevant
        return None

    # Concatenate all non-None string values from transcript_text
    text_parts: list[str] = []
    for value in transcript_text.values():
        if isinstance(value, str) and value.strip():
            text_parts.append(value)

    combined_text = " ".join(text_parts)
    if not combined_text.strip():
        return None

    # Count vague and substantive keywords
    matches = count_keywords_in_text(combined_text, _EARNINGS_PATTERNS)
    vague_count = sum(m.count for m in matches if m.tier == "vague")
    substantive_count = sum(m.count for m in matches if m.tier == "substantive")
    total_keywords = vague_count + substantive_count

    # Buzzword density ratio: proportion of vague terms
    buzzword_density_ratio = vague_count / max(total_keywords, 1)

    # Substantive ratio: proportion of substantive terms
    substantive_ratio = substantive_count / max(total_keywords, 1)

    # Sentiment mismatch: positive sentiment * (1 - substantive_ratio)
    # High positive sentiment + low substance = high mismatch (hype)
    sentiment_mismatch = sentiment_result.positive * (1.0 - substantive_ratio)

    # Raw combined score
    raw_score = buzzword_weight * buzzword_density_ratio + sentiment_weight * sentiment_mismatch

    # Normalize via sigmoid to 0-100
    score = sigmoid_normalize(raw_score, midpoint=sigmoid_midpoint, steepness=sigmoid_steepness)

    # Build evidence dict for audit trail
    evidence = {
        "signal_version": _EARNINGS_SIGNAL_VERSION,
        "buzzword_density_ratio": round(buzzword_density_ratio, 4),
        "vague_count": vague_count,
        "substantive_count": substantive_count,
        "sentiment": {
            "positive": round(sentiment_result.positive, 4),
            "negative": round(sentiment_result.negative, 4),
            "neutral": round(sentiment_result.neutral, 4),
        },
        "sentiment_mismatch": round(sentiment_mismatch, 4),
        "scoring_params": {
            "buzzword_weight": buzzword_weight,
            "sentiment_weight": sentiment_weight,
            "sigmoid_midpoint": sigmoid_midpoint,
            "sigmoid_steepness": sigmoid_steepness,
        },
        "ai_claim_intensity": ai_claim_intensity,
        "ai_claim_intensity_defaulted": ai_claim_intensity_defaulted,
        "raw_score": round(raw_score, 4),
    }

    return SignalResult(
        signal_type="earnings_vagueness",
        score=score,
        evidence=evidence,
    )
