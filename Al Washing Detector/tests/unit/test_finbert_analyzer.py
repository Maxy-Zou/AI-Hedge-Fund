"""Unit tests for FinBERT chunked sentiment analyzer.

Validates SentimentResult validation, chunked text splitting, sentiment
aggregation, empty text handling, and pipeline reuse -- all with mocked
transformers to avoid downloading the actual FinBERT model.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestSentimentResult:
    """Tests for SentimentResult Pydantic model."""

    def test_valid_probabilities_sum_to_one(self):
        from ai_washer.analysis.finbert_analyzer import SentimentResult

        result = SentimentResult(positive=0.7, negative=0.2, neutral=0.1)
        assert abs(result.positive + result.negative + result.neutral - 1.0) < 0.05

    def test_rejects_probabilities_not_summing_to_one(self):
        from ai_washer.analysis.finbert_analyzer import SentimentResult

        with pytest.raises(ValueError, match="sum"):
            SentimentResult(positive=0.5, negative=0.5, neutral=0.5)


class TestChunkTextForBert:
    """Tests for chunk_text_for_bert function."""

    def test_splits_long_text_into_correct_chunks(self):
        from ai_washer.analysis.finbert_analyzer import chunk_text_for_bert

        # Create a mock tokenizer
        tokenizer = MagicMock()
        # Simulate 1530 tokens (should become 3 chunks at max_tokens=510)
        fake_ids = list(range(1530))
        tokenizer.encode.return_value = fake_ids
        tokenizer.decode.side_effect = lambda ids, **kw: f"chunk_{len(ids)}"

        chunks = chunk_text_for_bert("some long text", tokenizer, max_tokens=510)
        assert len(chunks) == 3
        tokenizer.encode.assert_called_once()

    def test_single_chunk_for_short_text(self):
        from ai_washer.analysis.finbert_analyzer import chunk_text_for_bert

        tokenizer = MagicMock()
        tokenizer.encode.return_value = list(range(100))
        tokenizer.decode.side_effect = lambda ids, **kw: "short text"

        chunks = chunk_text_for_bert("short text", tokenizer, max_tokens=510)
        assert len(chunks) == 1


class TestFinBERTAnalyzer:
    """Tests for FinBERTAnalyzer class."""

    def _make_mock_pipeline(self):
        """Create a mock pipeline that returns FinBERT-style output."""
        mock_pipe = MagicMock()
        # Pipeline returns list of dicts for each input chunk
        mock_pipe.side_effect = lambda chunks, **kw: [
            {"label": "positive", "score": 0.7} for _ in chunks
        ]
        return mock_pipe

    def _make_mock_tokenizer(self, num_tokens: int = 100):
        """Create a mock tokenizer."""
        mock_tok = MagicMock()
        mock_tok.encode.return_value = list(range(num_tokens))
        mock_tok.decode.side_effect = lambda ids, **kw: "decoded chunk"
        return mock_tok

    @patch("ai_washer.analysis.finbert_analyzer.AutoTokenizer")
    @patch("ai_washer.analysis.finbert_analyzer.pipeline")
    def test_analyze_text_returns_valid_sentiment(self, mock_pipeline_fn, mock_auto_tok):
        from ai_washer.analysis.finbert_analyzer import FinBERTAnalyzer

        mock_pipe = self._make_mock_pipeline()
        mock_pipeline_fn.return_value = mock_pipe
        mock_auto_tok.from_pretrained.return_value = self._make_mock_tokenizer()

        analyzer = FinBERTAnalyzer()
        result = analyzer.analyze_text("The company reported strong AI revenue growth.")

        assert 0.0 <= result.positive <= 1.0
        assert 0.0 <= result.negative <= 1.0
        assert 0.0 <= result.neutral <= 1.0
        assert abs(result.positive + result.negative + result.neutral - 1.0) < 0.05

    @patch("ai_washer.analysis.finbert_analyzer.AutoTokenizer")
    @patch("ai_washer.analysis.finbert_analyzer.pipeline")
    def test_analyze_text_long_text_chunks_and_aggregates(self, mock_pipeline_fn, mock_auto_tok):
        from ai_washer.analysis.finbert_analyzer import FinBERTAnalyzer

        # First chunk: positive, second chunk: negative -- aggregation should mean them
        mock_pipe = MagicMock()
        mock_pipe.side_effect = lambda chunks, **kw: [
            {"label": "positive", "score": 0.8},
            {"label": "negative", "score": 0.6},
        ]
        mock_pipeline_fn.return_value = mock_pipe

        # Tokenizer returns 1020 tokens -> 2 chunks of 510
        mock_tok = self._make_mock_tokenizer(num_tokens=1020)
        mock_auto_tok.from_pretrained.return_value = mock_tok

        analyzer = FinBERTAnalyzer()
        result = analyzer.analyze_text("A very long earnings call transcript " * 200)

        # With 2 chunks: one positive (0.8) and one negative (0.6),
        # aggregated means should produce intermediate values
        assert result.positive > 0.0
        assert result.negative > 0.0
        assert abs(result.positive + result.negative + result.neutral - 1.0) < 0.05

    def test_analyze_text_empty_returns_neutral(self):
        from ai_washer.analysis.finbert_analyzer import FinBERTAnalyzer

        analyzer = FinBERTAnalyzer()
        result = analyzer.analyze_text("")

        assert result.positive == 0.0
        assert result.negative == 0.0
        assert result.neutral == 1.0

    @patch("ai_washer.analysis.finbert_analyzer.AutoTokenizer")
    @patch("ai_washer.analysis.finbert_analyzer.pipeline")
    def test_reuses_pipeline_instance(self, mock_pipeline_fn, mock_auto_tok):
        from ai_washer.analysis.finbert_analyzer import FinBERTAnalyzer

        mock_pipe = self._make_mock_pipeline()
        mock_pipeline_fn.return_value = mock_pipe
        mock_auto_tok.from_pretrained.return_value = self._make_mock_tokenizer()

        analyzer = FinBERTAnalyzer()
        analyzer.analyze_text("First call")
        analyzer.analyze_text("Second call")

        # Pipeline constructor called only once (lazy load, then reuse)
        assert mock_pipeline_fn.call_count == 1
        assert mock_auto_tok.from_pretrained.call_count == 1

    @patch("ai_washer.analysis.finbert_analyzer.AutoTokenizer")
    @patch("ai_washer.analysis.finbert_analyzer.pipeline")
    def test_analyze_segments(self, mock_pipeline_fn, mock_auto_tok):
        from ai_washer.analysis.finbert_analyzer import FinBERTAnalyzer

        mock_pipe = self._make_mock_pipeline()
        mock_pipeline_fn.return_value = mock_pipe
        mock_auto_tok.from_pretrained.return_value = self._make_mock_tokenizer()

        analyzer = FinBERTAnalyzer()
        segments = {
            "prepared_remarks": "We are excited about AI growth.",
            "qa": None,
            "summary": "Strong quarter ahead.",
        }
        results = analyzer.analyze_segments(segments)

        assert "prepared_remarks" in results
        assert "summary" in results
        # None segments should be skipped
        assert "qa" not in results
