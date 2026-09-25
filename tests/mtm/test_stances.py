"""Phase 11 T2 -- analyst stance derivation (11-SPEC A2) and debate snapshot."""

from __future__ import annotations

import pytest

from ai_hedge_fund.mtm.attribution import debate_snapshot, derive_stances
from ai_hedge_fund.mtm.policy import load_mtm_policy

POLICY = load_mtm_policy()  # sentiment_threshold 0.2


def _factors(analyst: str, bull: int, bear: int, **extra: object) -> dict:
    return {
        "analyst": analyst,
        "analysis": {"bull_factors": ["b"] * bull, "bear_factors": ["r"] * bear},
        "tokens_used": 10,
        **extra,
    }


def _sentiment(score: float, **extra: object) -> dict:
    return {
        "analyst": "sentiment",
        "analysis": {"composite_score": score},
        "tokens_used": 10,
        **extra,
    }


def _all(fund: dict, sent: dict, tech: dict) -> list[dict]:
    return [fund, sent, tech]


@pytest.mark.parametrize(
    ("bull", "bear", "stance"),
    [(3, 1, "bull"), (1, 3, "bear"), (2, 2, "neutral"), (0, 0, "neutral")],
)
@pytest.mark.parametrize("analyst", ["fundamental", "technical"])
def test_factor_count_rule(analyst: str, bull: int, bear: int, stance: str) -> None:
    stances = derive_stances([_factors(analyst, bull, bear)], POLICY)
    assert stances[analyst] == stance


@pytest.mark.parametrize(
    ("score", "stance"),
    [
        (0.2, "bull"),
        (0.9, "bull"),
        (0.19, "neutral"),
        (0.0, "neutral"),
        (-0.19, "neutral"),
        (-0.2, "bear"),
        (-1.0, "bear"),
    ],
)
def test_sentiment_threshold_rule(score: float, stance: str) -> None:
    assert derive_stances([_sentiment(score)], POLICY)["sentiment"] == stance


def test_always_returns_all_three_analysts() -> None:
    assert derive_stances([], POLICY) == {
        "fundamental": "absent",
        "sentiment": "absent",
        "technical": "absent",
    }


def test_errored_analyst_is_absent() -> None:
    """11-PREMORTEM #24: an analyst that failed has no view, not a neutral one."""
    reports = _all(
        _factors("fundamental", 3, 0, error="timeout"),
        _sentiment(0.9, error="rate limited"),
        _factors("technical", 0, 3, error="boom"),
    )
    assert set(derive_stances(reports, POLICY).values()) == {"absent"}


@pytest.mark.parametrize(
    "report",
    [
        {"analyst": "fundamental", "analysis": {}, "tokens_used": 1},
        {"analyst": "fundamental", "analysis": {"bull_factors": "x", "bear_factors": []}},
        {"analyst": "fundamental"},
        {"analyst": "sentiment", "analysis": {"composite_score": "high"}},
        {"analyst": "sentiment", "analysis": {"composite_score": True}},
        {"analyst": "sentiment", "analysis": {}},
    ],
    ids=["no-factors", "factors-not-list", "no-analysis", "score-str", "score-bool", "no-score"],
)
def test_malformed_report_is_absent(report: dict) -> None:
    assert derive_stances([report], POLICY)[report["analyst"]] == "absent"


def test_duplicate_reports_for_one_analyst_are_absent() -> None:
    """Two conflicting reports for one analyst: no honest single stance exists."""
    reports = [_factors("fundamental", 3, 0), _factors("fundamental", 0, 3)]
    assert derive_stances(reports, POLICY)["fundamental"] == "absent"


def test_unknown_analyst_ignored() -> None:
    stances = derive_stances([_factors("macro", 3, 0)], POLICY)
    assert "macro" not in stances


def test_debate_snapshot_reads_synthesis_fields() -> None:
    synthesis = {
        "pre_debate_confidence": 60,
        "post_debate_confidence": 72,
        "quality_score": 81,
        "synthesis_notes": "not copied",
    }
    assert debate_snapshot(synthesis) == {
        "pre_debate_confidence": 60,
        "post_debate_confidence": 72,
        "quality_score": 81,
    }


@pytest.mark.parametrize(
    "synthesis",
    [
        None,
        {},
        {"pre_debate_confidence": 60, "post_debate_confidence": 72},
        {"pre_debate_confidence": "60", "post_debate_confidence": 72, "quality_score": 81},
    ],
    ids=["none", "empty", "missing-quality", "str-confidence"],
)
def test_debate_snapshot_none_when_absent_or_malformed(synthesis: dict | None) -> None:
    """11-PREMORTEM #26: a run with no (usable) debate stores None, never crashes."""
    assert debate_snapshot(synthesis) is None


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_composite_is_absent(score: float) -> None:
    assert derive_stances([_sentiment(score)], POLICY)["sentiment"] == "absent"


def test_non_string_factor_items_are_absent() -> None:
    report = {
        "analyst": "technical",
        "analysis": {"bull_factors": [None, "", 3], "bear_factors": []},
    }
    assert derive_stances([report], POLICY)["technical"] == "absent"


def test_real_analyst_schemas_feed_the_rule() -> None:
    """Review M1: tie the rule to the real output schemas so a field rename fails a test."""
    from ai_hedge_fund.schemas.agents import (
        FundamentalAnalysis,
        SentimentAnalysis,
        TechnicalAnalysis,
    )

    def dump(model: type, **values: object) -> dict:
        fields = model.model_fields
        assert set(values) <= set(fields), f"{model.__name__} lost {set(values) - set(fields)}"
        return values

    reports = [
        {
            "analyst": "fundamental",
            "analysis": dump(FundamentalAnalysis, bull_factors=["a", "b"], bear_factors=["c"]),
        },
        {
            "analyst": "technical",
            "analysis": dump(TechnicalAnalysis, bull_factors=["a"], bear_factors=["b", "c"]),
        },
        {"analyst": "sentiment", "analysis": dump(SentimentAnalysis, composite_score=0.5)},
    ]
    assert derive_stances(reports, POLICY) == {
        "fundamental": "bull", "technical": "bear", "sentiment": "bull",
    }  # fmt: skip
