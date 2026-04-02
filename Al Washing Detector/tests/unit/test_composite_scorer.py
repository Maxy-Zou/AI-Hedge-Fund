"""Unit tests for composite scoring logic.

Tests weighted average computation, graceful degradation when signals are
missing, risk band classification, and signal-type-to-weight-key mapping.
"""

from __future__ import annotations

import pytest

from ai_washer.analysis.composite_scorer import (
    ALL_SIGNAL_TYPES,
    SIGNAL_TYPE_TO_WEIGHT_KEY,
    CompositeResult,
    classify_risk_band,
    compute_composite_score,
)
from ai_washer.analysis.types import SignalResult
from ai_washer.config import SignalWeights


def _make_signal(signal_type: str, score: int) -> SignalResult:
    return SignalResult(signal_type=signal_type, score=score, evidence={})


class TestCompositeScore:
    """Tests for compute_composite_score."""

    def test_all_six_signals_produces_weighted_average(self) -> None:
        weights = SignalWeights()
        signals = [
            _make_signal("sec_filing", 80),
            _make_signal("patent_gap", 60),
            _make_signal("earnings_vagueness", 70),
            _make_signal("job_mismatch", 50),
            _make_signal("github_activity", 40),
            _make_signal("compute_spending", 90),
        ]
        result = compute_composite_score(signals, weights)
        assert result is not None
        # 80*0.20 + 60*0.15 + 70*0.20 + 50*0.25 + 40*0.10 + 90*0.10
        # = 16 + 9 + 14 + 12.5 + 4 + 9 = 64.5 -> 64 (rounds)
        expected = round(
            80 * 0.20
            + 60 * 0.15
            + 70 * 0.20
            + 50 * 0.25
            + 40 * 0.10
            + 90 * 0.10
        )
        assert result.score == expected
        assert result.confidence == pytest.approx(1.0, abs=0.001)

    def test_single_signal_produces_score_with_low_confidence(self) -> None:
        weights = SignalWeights()
        signals = [_make_signal("sec_filing", 75)]
        result = compute_composite_score(signals, weights)
        assert result is not None
        assert result.score == 75
        assert result.confidence == pytest.approx(0.20, abs=0.001)

    def test_missing_signals_renormalize_weights(self) -> None:
        weights = SignalWeights()
        # sec_filing=0.20, patent_gap=0.15, earnings_vagueness->earnings_call=0.20
        # original sum = 0.55
        signals = [
            _make_signal("sec_filing", 80),
            _make_signal("patent_gap", 60),
            _make_signal("earnings_vagueness", 40),
        ]
        result = compute_composite_score(signals, weights)
        assert result is not None
        assert result.confidence == pytest.approx(0.55, abs=0.001)
        # renormalized: sec=0.20/0.55, patent=0.15/0.55, earnings=0.20/0.55
        expected = round(
            80 * (0.20 / 0.55)
            + 60 * (0.15 / 0.55)
            + 40 * (0.20 / 0.55)
        )
        assert result.score == expected
        assert len(result.signals_available) == 3
        assert len(result.signals_missing) == 3

    def test_empty_signals_returns_none(self) -> None:
        weights = SignalWeights()
        result = compute_composite_score([], weights)
        assert result is None

    def test_composite_score_clamped_0_100(self) -> None:
        weights = SignalWeights()
        # Scores above 100 should be clamped
        signals = [_make_signal("sec_filing", 150)]
        result = compute_composite_score(signals, weights)
        assert result is not None
        assert 0 <= result.score <= 100

    def test_signals_available_and_missing(self) -> None:
        weights = SignalWeights()
        signals = [
            _make_signal("sec_filing", 50),
            _make_signal("github_activity", 60),
        ]
        result = compute_composite_score(signals, weights)
        assert result is not None
        assert sorted(result.signals_available) == ["github_activity", "sec_filing"]
        assert "patent_gap" in result.signals_missing
        assert "earnings_vagueness" in result.signals_missing
        assert "job_mismatch" in result.signals_missing
        assert "compute_spending" in result.signals_missing


class TestRiskBandClassification:
    """Tests for classify_risk_band."""

    def test_risk_band_genuine(self) -> None:
        assert classify_risk_band(15) == "genuine"

    def test_risk_band_mixed(self) -> None:
        assert classify_risk_band(45) == "mixed"

    def test_risk_band_significant_risk(self) -> None:
        assert classify_risk_band(70) == "significant_risk"

    def test_risk_band_strong_short(self) -> None:
        assert classify_risk_band(90) == "strong_short"

    def test_risk_band_boundary_30(self) -> None:
        assert classify_risk_band(30) == "mixed"

    def test_risk_band_boundary_60(self) -> None:
        assert classify_risk_band(60) == "significant_risk"

    def test_risk_band_boundary_80(self) -> None:
        assert classify_risk_band(80) == "strong_short"

    def test_risk_band_zero(self) -> None:
        assert classify_risk_band(0) == "genuine"

    def test_risk_band_100(self) -> None:
        assert classify_risk_band(100) == "strong_short"


class TestSignalTypeMapping:
    """Tests for SIGNAL_TYPE_TO_WEIGHT_KEY constant."""

    def test_signal_type_to_weight_mapping_covers_all_six(self) -> None:
        assert len(SIGNAL_TYPE_TO_WEIGHT_KEY) == 6

    def test_earnings_vagueness_maps_to_earnings_call(self) -> None:
        assert SIGNAL_TYPE_TO_WEIGHT_KEY["earnings_vagueness"] == "earnings_call"

    def test_job_mismatch_maps_to_job_posting(self) -> None:
        assert SIGNAL_TYPE_TO_WEIGHT_KEY["job_mismatch"] == "job_posting"

    def test_all_signal_types_has_six(self) -> None:
        assert len(ALL_SIGNAL_TYPES) == 6

    def test_all_signal_types_matches_keys(self) -> None:
        assert set(ALL_SIGNAL_TYPES) == set(SIGNAL_TYPE_TO_WEIGHT_KEY.keys())
