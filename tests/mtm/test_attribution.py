"""Phase 11 T6 -- attribution labels per signal and the exact integer split (11-SPEC s5, D3)."""

from __future__ import annotations

import json
import random

import pytest

from ai_hedge_fund.mtm.attribution import (
    Attribution,
    attribution_for,
    debate_winner,
    split_cents,
)
from ai_hedge_fund.mtm.policy import load_mtm_policy

POLICY = load_mtm_policy()


def _v2(stances: dict[str, str], debate: dict | None = None) -> dict:
    return {"schema_version": 2, "analyst_stances": stances, "debate": debate}


DEBATE_UP = {"pre_debate_confidence": 60, "post_debate_confidence": 72, "quality_score": 80}
DEBATE_DOWN = {"pre_debate_confidence": 72, "post_debate_confidence": 60, "quality_score": 80}
DEBATE_FLAT = {"pre_debate_confidence": 65, "post_debate_confidence": 65, "quality_score": 80}


@pytest.mark.parametrize(
    ("debate", "side", "winner"),
    [
        (DEBATE_UP, "buy", "bull"),
        (DEBATE_DOWN, "buy", "bear"),
        (DEBATE_FLAT, "buy", "draw"),
        (DEBATE_UP, "sell", "bear"),
        (DEBATE_DOWN, "sell", "bull"),
        (None, "buy", "unattributed"),
    ],
)
def test_debate_winner_table(debate: dict | None, side: str, winner: str) -> None:
    """11-PREMORTEM #25 / D3: who moved the thesis toward (or away from) the traded side."""
    assert debate_winner(debate, side) == winner  # type: ignore[arg-type]


def test_credited_analysts_are_those_aligned_with_the_side() -> None:
    stances = {"fundamental": "bull", "sentiment": "bear", "technical": "bull"}
    a = attribution_for(_v2(stances, DEBATE_UP), confidence=80, side="buy", policy=POLICY)
    assert a == Attribution(
        attribution_schema="v2",
        credited_analysts=("fundamental", "technical"),
        debate_winner="bull",
        conviction_bucket="high",
    )
    s = attribution_for(_v2(stances, DEBATE_UP), confidence=80, side="sell", policy=POLICY)
    assert s.credited_analysts == ("sentiment",)


def test_neutral_and_absent_are_never_credited() -> None:
    stances = {"fundamental": "neutral", "sentiment": "absent", "technical": "bear"}
    a = attribution_for(_v2(stances), confidence=50, side="buy", policy=POLICY)
    assert a.credited_analysts == ()
    assert a.attribution_schema == "v2"  # none_aligned, not unattributed
    assert a.debate_winner == "unattributed"  # v2 row without a debate


def test_v1_payload_is_unattributed() -> None:
    """11-PREMORTEM #22: an old analysis has no stances; never bucket it as none_aligned."""
    v1 = {"schema_version": 1, "thesis": {}, "signal": {}}
    a = attribution_for(v1, confidence=55, side="buy", policy=POLICY)
    assert a == Attribution(
        attribution_schema="unattributed",
        credited_analysts=(),
        debate_winner="unattributed",
        conviction_bucket="medium",  # conviction is stored in v1 too
    )


def test_uses_stored_stances_not_rederived() -> None:
    """11-PREMORTEM #23: the frozen stances win over anything else in the payload."""
    payload = _v2({"fundamental": "bull", "sentiment": "bull", "technical": "bull"})
    payload["analyst_reports"] = [
        {"analyst": "fundamental", "analysis": {"bull_factors": [], "bear_factors": ["x"]}}
    ]
    a = attribution_for(payload, confidence=90, side="buy", policy=POLICY)
    assert a.credited_analysts == ("fundamental", "sentiment", "technical")


def test_null_confidence_is_unknown_bucket() -> None:
    a = attribution_for(_v2({}), confidence=None, side="buy", policy=POLICY)
    assert a.conviction_bucket == "unknown"


def test_malformed_v2_stances_fall_back_to_unattributed() -> None:
    a = attribution_for(
        {"schema_version": 2, "analyst_stances": "bull"}, confidence=60, side="buy", policy=POLICY
    )
    assert a.attribution_schema == "unattributed"


def test_no_float_in_attribution() -> None:
    """11-PREMORTEM #5: the stored JSON is deterministic -- no floats, stable key order."""
    a = attribution_for(_v2({"fundamental": "bull"}, DEBATE_UP), 80, "buy", POLICY)
    dumped = a.model_dump(mode="json")
    assert not any(isinstance(v, float) for v in dumped.values())
    assert json.dumps(dumped, sort_keys=True) == json.dumps(
        attribution_for(_v2({"fundamental": "bull"}, DEBATE_UP), 80, "buy", POLICY).model_dump(
            mode="json"
        ),
        sort_keys=True,
    )


@pytest.mark.parametrize(
    ("total", "parts", "expected"),
    [
        (10, 3, (4, 3, 3)),
        (-10, 3, (-3, -3, -4)),
        (2, 3, (1, 1, 0)),
        (0, 2, (0, 0)),
        (7, 1, (7,)),
    ],
)
def test_split_cents_table(total: int, parts: int, expected: tuple[int, ...]) -> None:
    assert split_cents(total, parts) == expected


def test_split_cents_always_sums_exactly() -> None:
    """11-PREMORTEM #21 (core): remainder cents are assigned, never dropped."""
    rng = random.Random(11)
    for _ in range(2_000):
        total, parts = rng.randint(-(10**9), 10**9), rng.randint(1, 3)
        pieces = split_cents(total, parts)
        assert sum(pieces) == total and len(pieces) == parts
        assert max(pieces) - min(pieces) <= 1


def test_split_cents_rejects_zero_parts() -> None:
    with pytest.raises(ValueError):
        split_cents(10, 0)
