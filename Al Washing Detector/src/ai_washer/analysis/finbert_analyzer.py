"""FinBERT chunked sentiment analyzer for earnings call text.

Provides:
- SentimentResult: Pydantic model with positive/negative/neutral probabilities
- chunk_text_for_bert: Split text into 510-token segments for BERT models
- FinBERTAnalyzer: Lazy-loading sentiment analyzer with mean aggregation

The analyzer handles text of any length by chunking into 510-token segments
(BERT max is 512, minus 2 for [CLS] and [SEP] tokens), running FinBERT
inference on each chunk, and aggregating probabilities via arithmetic mean.

Usage:
    analyzer = FinBERTAnalyzer()
    result = analyzer.analyze_text("Company reported strong AI revenue.")
    print(result.positive, result.negative, result.neutral)
"""

from __future__ import annotations

import structlog
from pydantic import BaseModel, model_validator
from transformers import AutoTokenizer, pipeline  # type: ignore[import-untyped]

logger = structlog.get_logger(__name__)

# Label mapping from FinBERT output to SentimentResult fields
_LABEL_MAP = {"positive": "positive", "negative": "negative", "neutral": "neutral"}

# All valid sentiment labels
_VALID_LABELS = frozenset(_LABEL_MAP.values())


class SentimentResult(BaseModel):
    """Sentiment probabilities from FinBERT inference.

    Fields sum to approximately 1.0 (tolerance 0.05 for floating point).
    """

    positive: float
    negative: float
    neutral: float

    @model_validator(mode="after")
    def _check_sum_to_one(self) -> SentimentResult:
        total = self.positive + self.negative + self.neutral
        if abs(total - 1.0) > 0.05:
            msg = f"Probabilities must sum to ~1.0 (got {total:.4f})"
            raise ValueError(msg)
        return self


def chunk_text_for_bert(
    text: str,
    tokenizer: AutoTokenizer,
    max_tokens: int = 510,
) -> list[str]:
    """Split text into chunks that fit within BERT token limits.

    Encodes text without special tokens, splits token IDs into segments
    of max_tokens, then decodes each segment back to text.

    Args:
        text: Input text to chunk.
        tokenizer: HuggingFace tokenizer instance.
        max_tokens: Maximum tokens per chunk (default 510 for BERT).

    Returns:
        List of text chunks, each within token limits.
    """
    token_ids: list[int] = tokenizer.encode(text, add_special_tokens=False)

    if not token_ids:
        return [text] if text.strip() else []

    chunks: list[str] = []
    for start in range(0, len(token_ids), max_tokens):
        chunk_ids = token_ids[start : start + max_tokens]
        decoded = tokenizer.decode(chunk_ids, skip_special_tokens=True)
        chunks.append(decoded)

    return chunks


class FinBERTAnalyzer:
    """Lazy-loading FinBERT sentiment analyzer with chunked inference.

    Loads the model and tokenizer on first use. Subsequent calls reuse
    the same pipeline instance for efficiency.

    Args:
        model_name: HuggingFace model identifier. Defaults to ProsusAI/finbert.
    """

    def __init__(self, model_name: str = "ProsusAI/finbert") -> None:
        self._model_name = model_name
        self._pipe = None
        self._tokenizer = None

    def _ensure_loaded(self) -> None:
        """Load model and tokenizer on first use."""
        if self._pipe is not None:
            return

        logger.info(
            "finbert_model_loading",
            model=self._model_name,
        )
        self._pipe = pipeline(
            "sentiment-analysis",
            model=self._model_name,
            tokenizer=self._model_name,
            batch_size=8,
            truncation=True,
            max_length=512,
        )
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
        logger.info("finbert_model_loaded", model=self._model_name)

    def analyze_text(self, text: str) -> SentimentResult:
        """Analyze text sentiment using FinBERT with chunked aggregation.

        Empty text returns neutral-dominant result. Long text is chunked
        into 510-token segments; per-chunk predictions are aggregated via
        arithmetic mean across all chunks.

        Args:
            text: Text to analyze (any length).

        Returns:
            SentimentResult with aggregated positive/negative/neutral probabilities.
        """
        if not text or not text.strip():
            return SentimentResult(positive=0.0, negative=0.0, neutral=1.0)

        self._ensure_loaded()
        assert self._pipe is not None
        assert self._tokenizer is not None

        chunks = chunk_text_for_bert(text, self._tokenizer, max_tokens=510)

        if not chunks:
            return SentimentResult(positive=0.0, negative=0.0, neutral=1.0)

        # Run pipeline on all chunks
        predictions = self._pipe(chunks)

        # Aggregate: accumulate probabilities per label, then compute mean
        totals: dict[str, float] = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
        num_chunks = len(predictions)

        for pred in predictions:
            label = _LABEL_MAP.get(pred["label"], pred["label"])
            score = pred["score"]
            # FinBERT returns only the top label and its score;
            # distribute remaining probability equally across other labels
            remaining = 1.0 - score
            for lbl in _VALID_LABELS:
                if lbl == label:
                    totals[lbl] += score
                else:
                    totals[lbl] += remaining / 2.0

        # Compute mean across chunks
        result = SentimentResult(
            positive=totals["positive"] / num_chunks,
            negative=totals["negative"] / num_chunks,
            neutral=totals["neutral"] / num_chunks,
        )

        logger.debug(
            "finbert_analysis_complete",
            num_chunks=num_chunks,
            positive=round(result.positive, 4),
            negative=round(result.negative, 4),
            neutral=round(result.neutral, 4),
        )

        return result

    def analyze_segments(
        self, segments: dict[str, str | None]
    ) -> dict[str, SentimentResult]:
        """Analyze sentiment for multiple named text segments.

        Skips segments with None values.

        Args:
            segments: Mapping of segment name to text content.

        Returns:
            Dict of segment name to SentimentResult for non-None segments.
        """
        results: dict[str, SentimentResult] = {}
        for name, text in segments.items():
            if text is not None:
                results[name] = self.analyze_text(text)
        return results
