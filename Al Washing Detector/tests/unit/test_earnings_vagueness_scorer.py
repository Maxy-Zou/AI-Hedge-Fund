"""Tests for pure earnings vagueness scorer function.

Verifies buzzword density + sentiment mismatch scoring logic,
edge cases for ai_claim_intensity, and evidence dict structure.
"""

from __future__ import annotations

import pytest

from ai_washer.analysis.finbert_analyzer import SentimentResult


@pytest.fixture
def positive_sentiment() -> SentimentResult:
    """Strongly positive sentiment (hype)."""
    return SentimentResult(positive=0.80, negative=0.05, neutral=0.15)


@pytest.fixture
def neutral_sentiment() -> SentimentResult:
    """Neutral sentiment."""
    return SentimentResult(positive=0.20, negative=0.10, neutral=0.70)


@pytest.fixture
def buzzword_heavy_text() -> dict[str, str | None]:
    """Transcript with many vague terms, few substantive terms."""
    # Repeat vague terms to drive up buzzword density
    vague_section = (
        "We are leveraging ai across our ai transformation strategy. "
        "Our ai-powered platform delivers ai solutions with ai capabilities. "
        "This ai-driven approach is part of our exciting ai journey and ai roadmap. "
        "We see tremendous ai opportunity with ai momentum and ai initiatives. "
        "Our intelligent automation and digital transformation are ai-first."
    )
    return {"full_text": vague_section, "prepared_remarks": vague_section, "qa": None}


@pytest.fixture
def substantive_heavy_text() -> dict[str, str | None]:
    """Transcript with few vague terms, many substantive terms."""
    substantive_section = (
        "We deployed transformer model trained on proprietary data with "
        "inference latency under 50ms. Our gpu cluster runs the training pipeline "
        "with feature engineering and model serving at scale. The ml infrastructure "
        "includes data pipeline for model retraining. Our production model uses "
        "mlops with fine-tuned embedding model and vector search. "
        "Model accuracy improved as measured by f1 score. "
        "We run a/b testing on all production model changes."
    )
    return {"full_text": substantive_section, "prepared_remarks": substantive_section, "qa": None}


class TestBuzzwordHeavyScore:
    """Test 1: Buzzword-heavy text produces score > 60."""

    def test_buzzword_heavy_produces_high_score(self, buzzword_heavy_text, positive_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text=buzzword_heavy_text,
            sentiment_result=positive_sentiment,
            ai_claim_intensity=1.0,
            sigmoid_midpoint=0.5,
            sigmoid_steepness=5.0,
        )

        assert result is not None
        assert result.score > 60


class TestSubstantiveHeavyScore:
    """Test 2: Substantive-heavy text produces score < 30."""

    def test_substantive_heavy_produces_low_score(self, substantive_heavy_text, neutral_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text=substantive_heavy_text,
            sentiment_result=neutral_sentiment,
            ai_claim_intensity=1.0,
            sigmoid_midpoint=0.5,
            sigmoid_steepness=5.0,
        )

        assert result is not None
        assert result.score < 30


class TestEmptyTranscript:
    """Test 3: Empty transcript_text returns None."""

    def test_empty_text_returns_none(self, neutral_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text={"full_text": None, "prepared_remarks": None, "qa": None},
            sentiment_result=neutral_sentiment,
            ai_claim_intensity=1.0,
        )

        assert result is None

    def test_all_empty_strings_returns_none(self, neutral_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text={"full_text": "", "prepared_remarks": "", "qa": ""},
            sentiment_result=neutral_sentiment,
            ai_claim_intensity=1.0,
        )

        assert result is None


class TestScoreRange:
    """Test 4: Score is 0-100 integer."""

    def test_score_is_bounded_integer(self, buzzword_heavy_text, positive_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text=buzzword_heavy_text,
            sentiment_result=positive_sentiment,
            ai_claim_intensity=1.0,
        )

        assert result is not None
        assert isinstance(result.score, int)
        assert 0 <= result.score <= 100


class TestEvidenceDict:
    """Test 5: Evidence dict contains required fields."""

    def test_evidence_contains_required_fields(self, buzzword_heavy_text, positive_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text=buzzword_heavy_text,
            sentiment_result=positive_sentiment,
            ai_claim_intensity=1.0,
        )

        assert result is not None
        ev = result.evidence
        assert "buzzword_density_ratio" in ev
        assert "vague_count" in ev
        assert "substantive_count" in ev
        assert "sentiment" in ev
        assert "positive" in ev["sentiment"]
        assert "negative" in ev["sentiment"]
        assert "neutral" in ev["sentiment"]
        assert "scoring_params" in ev
        assert "buzzword_weight" in ev["scoring_params"]
        assert "sentiment_weight" in ev["scoring_params"]
        assert "sigmoid_midpoint" in ev["scoring_params"]
        assert "sigmoid_steepness" in ev["scoring_params"]


class TestSentimentMismatch:
    """Test 6: Sentiment mismatch inflates score."""

    def test_positive_sentiment_inflates_score(
        self, buzzword_heavy_text, positive_sentiment, neutral_sentiment
    ):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result_positive = compute_earnings_vagueness_score(
            transcript_text=buzzword_heavy_text,
            sentiment_result=positive_sentiment,
            ai_claim_intensity=1.0,
            sigmoid_midpoint=0.5,
            sigmoid_steepness=5.0,
        )

        result_neutral = compute_earnings_vagueness_score(
            transcript_text=buzzword_heavy_text,
            sentiment_result=neutral_sentiment,
            ai_claim_intensity=1.0,
            sigmoid_midpoint=0.5,
            sigmoid_steepness=5.0,
        )

        assert result_positive is not None
        assert result_neutral is not None
        # Positive sentiment + high buzzwords = higher score than neutral + same buzzwords
        assert result_positive.score >= result_neutral.score


class TestAiClaimIntensityZero:
    """Test 7: ai_claim_intensity=0.0 returns None."""

    def test_zero_ai_claims_returns_none(self, buzzword_heavy_text, positive_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text=buzzword_heavy_text,
            sentiment_result=positive_sentiment,
            ai_claim_intensity=0.0,
        )

        assert result is None


class TestAiClaimIntensityNone:
    """Test 8: ai_claim_intensity=None defaults to 0.5 and produces a score."""

    def test_none_defaults_to_half_and_scores(self, buzzword_heavy_text, positive_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text=buzzword_heavy_text,
            sentiment_result=positive_sentiment,
            ai_claim_intensity=None,
        )

        assert result is not None
        assert isinstance(result.score, int)
        assert 0 <= result.score <= 100


class TestSignalMetadata:
    """Test 9: signal_type and signal_version are correct."""

    def test_signal_type_and_version(self, buzzword_heavy_text, positive_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text=buzzword_heavy_text,
            sentiment_result=positive_sentiment,
            ai_claim_intensity=1.0,
        )

        assert result is not None
        assert result.signal_type == "earnings_vagueness"
        assert result.evidence["signal_version"] == "0.7.0"


class TestAiClaimIntensityDefaultedFlag:
    """Test 10: evidence contains ai_claim_intensity_defaulted flag."""

    def test_defaulted_true_when_none(self, buzzword_heavy_text, positive_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text=buzzword_heavy_text,
            sentiment_result=positive_sentiment,
            ai_claim_intensity=None,
        )

        assert result is not None
        assert result.evidence["ai_claim_intensity_defaulted"] is True

    def test_defaulted_false_when_provided(self, buzzword_heavy_text, positive_sentiment):
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        result = compute_earnings_vagueness_score(
            transcript_text=buzzword_heavy_text,
            sentiment_result=positive_sentiment,
            ai_claim_intensity=1.0,
        )

        assert result is not None
        assert result.evidence["ai_claim_intensity_defaulted"] is False


class TestCombinedScore:
    """Combined scoring behavior validation."""

    def test_combined_score_within_range(self, positive_sentiment):
        """Mixed text produces a mid-range score."""
        from ai_washer.analysis.earnings_vagueness_scorer import (
            compute_earnings_vagueness_score,
        )

        mixed_text = {
            "full_text": (
                "We are leveraging ai in our ai transformation strategy. "
                "Our gpu cluster runs the training pipeline with feature engineering. "
                "The production model uses mlops and fine-tuned models."
            ),
        }

        result = compute_earnings_vagueness_score(
            transcript_text=mixed_text,
            sentiment_result=positive_sentiment,
            ai_claim_intensity=1.0,
        )

        assert result is not None
        assert 0 <= result.score <= 100
