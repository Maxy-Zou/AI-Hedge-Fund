"""Tests for the deterministic self-critique math (Plan 07-04 Task 1).

Covers :func:`ai_hedge_fund.memory.critique.compute_new_confidence` (pure
function: old_confidence + outcome_pct + signal_direction -> new_confidence,
bounded [0, 100], per-event |delta| <= 10 per Pitfall 5) and
:func:`format_critique_context` (deterministic 5-section prompt).

The function must be algebraically simple and auditable:
    agreed outcome  (long+pos, short+neg) -> confidence raises
    disagreed       (long+neg, short+pos) -> confidence lowers
    neutral + move                         -> confidence lowers
    unknown direction                      -> ValueError

See 07-RESEARCH.md Pattern 6 and Pitfall 5 for the motivating contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_hedge_fund.memory.critique import (
    compute_new_confidence,
    format_critique_context,
)
from ai_hedge_fund.schemas.memory import Belief

# ---------- Agreement / disagreement on long ----------


def test_agreement_raises_long_confidence() -> None:
    result = compute_new_confidence(old_confidence=50, outcome_pct=2.0, signal_direction="long")
    assert isinstance(result, int)
    assert result > 50


def test_disagreement_lowers_long_confidence() -> None:
    result = compute_new_confidence(old_confidence=50, outcome_pct=-2.0, signal_direction="long")
    assert result < 50


# ---------- Agreement / disagreement on short ----------


def test_agreement_raises_short_confidence() -> None:
    # Short call + negative outcome = agreed -> confidence rises.
    result = compute_new_confidence(old_confidence=50, outcome_pct=-2.0, signal_direction="short")
    assert result > 50


def test_disagreement_lowers_short_confidence() -> None:
    # Short call + positive outcome = disagreed -> confidence falls.
    result = compute_new_confidence(old_confidence=50, outcome_pct=+2.0, signal_direction="short")
    assert result < 50


# ---------- Neutral ----------


def test_neutral_with_big_move_penalises_confidence() -> None:
    # Any significant move penalises a neutral call.
    result = compute_new_confidence(old_confidence=50, outcome_pct=+5.0, signal_direction="neutral")
    assert result < 50


def test_neutral_with_small_move_barely_moves() -> None:
    # Small move -> small adjustment, result <= 50 but close.
    result = compute_new_confidence(old_confidence=50, outcome_pct=+0.1, signal_direction="neutral")
    assert result <= 50
    assert abs(result - 50) <= 1  # 0.3 * 0.1 * 10 = 0.3 -> rounds to 0.


# ---------- Bounds: [0, 100] clamp ----------


def test_lower_bound_clamped_at_zero() -> None:
    # Big negative outcome on long call -> floor at 0 (would be -30 unclamped).
    # But with per-event cap of 10, it is old - 10 = -10 -> 0. Still 0.
    result = compute_new_confidence(old_confidence=0, outcome_pct=-10.0, signal_direction="long")
    assert result == 0


def test_upper_bound_clamped_at_hundred() -> None:
    # Big positive outcome on long call from ceiling -> stays 100.
    result = compute_new_confidence(old_confidence=100, outcome_pct=+10.0, signal_direction="long")
    assert result == 100


# ---------- Per-event cap (Pitfall 5 drift guard) ----------


def test_per_event_cap_prevents_oversized_jumps() -> None:
    # Without the cap: 50 + 0.3 * 50 * 10 = 200 -> clamped to 100.
    # With the cap (10): 50 + 10 = 60. This is THE Pitfall 5 regression.
    result = compute_new_confidence(old_confidence=50, outcome_pct=50.0, signal_direction="long")
    assert result == 60


def test_per_event_cap_symmetric_on_disagreement() -> None:
    # Large adverse move should still only subtract 10, not saturate at 0.
    result = compute_new_confidence(old_confidence=50, outcome_pct=50.0, signal_direction="short")
    assert result == 40


# ---------- Error path ----------


def test_unknown_direction_raises() -> None:
    with pytest.raises(ValueError, match="long"):
        compute_new_confidence(old_confidence=50, outcome_pct=1.0, signal_direction="bullish")


def test_unknown_direction_mentions_allowed_values() -> None:
    with pytest.raises(ValueError) as exc_info:
        compute_new_confidence(old_confidence=50, outcome_pct=1.0, signal_direction="UP")
    msg = str(exc_info.value)
    assert "short" in msg
    assert "neutral" in msg


# ---------- Property test: always bounded int ----------


@pytest.mark.parametrize("old", [0, 25, 50, 75, 100])
@pytest.mark.parametrize("outcome", [-10.0, -1.0, 0.0, 1.0, 10.0])
@pytest.mark.parametrize("direction", ["long", "short", "neutral"])
def test_result_bounded_to_unit_interval(old: int, outcome: float, direction: str) -> None:
    result = compute_new_confidence(
        old_confidence=old, outcome_pct=outcome, signal_direction=direction
    )
    assert isinstance(result, int)
    assert 0 <= result <= 100


# ---------- format_critique_context ----------


def _load_belief_from_fixture(path: Path) -> Belief:
    """Load a Belief from the golden YAML without pulling in belief I/O."""
    from ruamel.yaml import YAML

    parser = YAML()
    raw = parser.load(path)
    return Belief.model_validate(dict(raw))


def test_format_critique_context_sections(sample_belief_yaml_path: Path) -> None:
    belief = _load_belief_from_fixture(sample_belief_yaml_path)
    out = format_critique_context(belief=belief, outcome_pct=4.2, new_confidence=75)
    assert "BELIEF:" in out
    assert "OUTCOME:" in out
    assert "OLD_CONFIDENCE:" in out
    assert "NEW_CONFIDENCE (DETERMINISTIC):" in out
    assert "LINKED_ANALYSIS:" in out
    # 5 sections = 4 separators.
    assert out.count("\n\n---\n\n") == 4


def test_format_critique_context_is_deterministic(
    sample_belief_yaml_path: Path,
) -> None:
    belief = _load_belief_from_fixture(sample_belief_yaml_path)
    out1 = format_critique_context(belief=belief, outcome_pct=4.2, new_confidence=75)
    out2 = format_critique_context(belief=belief, outcome_pct=4.2, new_confidence=75)
    assert out1 == out2


def test_format_critique_context_includes_old_confidence(
    sample_belief_yaml_path: Path,
) -> None:
    belief = _load_belief_from_fixture(sample_belief_yaml_path)
    # Fixture has confidence=72.
    out = format_critique_context(belief=belief, outcome_pct=4.2, new_confidence=82)
    assert "OLD_CONFIDENCE: 72" in out
    assert "NEW_CONFIDENCE (DETERMINISTIC): 82" in out


def test_format_critique_context_includes_outcome_pct(
    sample_belief_yaml_path: Path,
) -> None:
    belief = _load_belief_from_fixture(sample_belief_yaml_path)
    out = format_critique_context(belief=belief, outcome_pct=-3.5, new_confidence=62)
    assert "-3.5" in out


def test_format_critique_context_accepts_empty_linked_analysis(
    sample_belief_yaml_path: Path,
) -> None:
    belief = _load_belief_from_fixture(sample_belief_yaml_path)
    out = format_critique_context(
        belief=belief,
        outcome_pct=1.0,
        new_confidence=73,
        linked_analysis_payload=None,
    )
    assert "LINKED_ANALYSIS:" in out


def test_format_critique_context_includes_linked_payload_keys(
    sample_belief_yaml_path: Path,
) -> None:
    belief = _load_belief_from_fixture(sample_belief_yaml_path)
    out = format_critique_context(
        belief=belief,
        outcome_pct=1.0,
        new_confidence=73,
        linked_analysis_payload={"direction": "long", "confidence": 72},
    )
    assert "direction" in out
    assert "long" in out
