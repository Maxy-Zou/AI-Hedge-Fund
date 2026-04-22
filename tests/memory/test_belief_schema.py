"""Schema tests for Belief + CritiqueEvent (Phase 7, MEM-02).

Covers the ``extra="forbid"`` contract (Pitfall 4 typo regression),
bounded lengths (DoS guards per Shared Pattern F), frozen distinctions
(CritiqueEvent immutable, Belief mutable for in-place copy), and the
YAML round-trip of the golden belief fixture.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from ruamel.yaml import YAML

from ai_hedge_fund.schemas.memory import Belief, CritiqueEvent


def _valid_belief_kwargs() -> dict:
    """Minimal valid Belief constructor kwargs (for negative tests)."""
    return {
        "ticker": "AAPL",
        "sector": "Technology",
        "version": 1,
        "thesis": "x",
        "confidence": 50,
    }


def test_valid_yaml_loads_to_model(sample_belief_yaml_path: Path) -> None:
    """Test 1: golden fixture validates and populates all fields."""
    yaml = YAML()
    raw = yaml.load(sample_belief_yaml_path)
    belief = Belief.model_validate(dict(raw))

    assert belief.ticker == "AAPL"
    assert belief.sector == "Technology"
    assert belief.version == 3
    assert belief.confidence == 72
    assert belief.human_edited is False
    assert belief.edited_at is None
    assert len(belief.critique_history) == 2
    assert belief.critique_history[0].as_of_date == date(2026, 3, 15)
    assert belief.critique_history[0].source == "self_critique"
    # field_locks dict fully populated from YAML
    assert belief.field_locks == {
        "thesis": False,
        "confidence": False,
        "sector": True,
    }


def test_unknown_key_raises_pitfall_4() -> None:
    """Test 2 (Pitfall 4 regression): typo 'confidance' raises ValidationError."""
    bad = _valid_belief_kwargs()
    bad["confidance"] = 72  # typo — MUST NOT silently shadow 'confidence'
    with pytest.raises(ValidationError):
        Belief.model_validate(bad)


def test_critique_event_source_pattern() -> None:
    """Test 3: source must match ``^(self_critique|human)$`` exactly."""
    # Valid sources accepted
    CritiqueEvent(
        as_of_date=date(2026, 4, 20),
        outcome_pct=4.2,
        old_confidence=70,
        new_confidence=72,
        rationale="x",
        source="self_critique",
    )
    CritiqueEvent(
        as_of_date=date(2026, 4, 20),
        outcome_pct=-1.0,
        old_confidence=70,
        new_confidence=65,
        rationale="y",
        source="human",
    )

    # Invalid source rejected
    with pytest.raises(ValidationError):
        CritiqueEvent(
            as_of_date=date(2026, 4, 20),
            outcome_pct=4.2,
            old_confidence=70,
            new_confidence=72,
            rationale="x",
            source="machine",  # not in the allowed set
        )


def test_critique_event_is_frozen() -> None:
    """Test 4: CritiqueEvent is immutable (frozen=True)."""
    event = CritiqueEvent(
        as_of_date=date(2026, 4, 20),
        outcome_pct=4.2,
        old_confidence=70,
        new_confidence=72,
        rationale="x",
        source="self_critique",
    )
    with pytest.raises(ValidationError):
        event.rationale = "mutated"


def test_belief_is_not_frozen() -> None:
    """Test 5: Belief is NOT frozen — writer replaces via file rewrite, not in-place."""
    belief = Belief(**_valid_belief_kwargs())
    # Must NOT raise — Belief is deliberately not frozen
    belief.confidence = 30
    assert belief.confidence == 30


def test_confidence_bounds() -> None:
    """Test 6: confidence must be in [0, 100]."""
    with pytest.raises(ValidationError):
        Belief.model_validate({**_valid_belief_kwargs(), "confidence": 101})
    with pytest.raises(ValidationError):
        Belief.model_validate({**_valid_belief_kwargs(), "confidence": -1})


def test_thesis_min_length() -> None:
    """Test 7: thesis cannot be empty (min_length=1)."""
    with pytest.raises(ValidationError):
        Belief.model_validate({**_valid_belief_kwargs(), "thesis": ""})


def test_round_trip_model_dump_equals() -> None:
    """Test 8: model_dump → model_validate round-trips cleanly."""
    belief = Belief(
        **_valid_belief_kwargs(),
        critique_history=[
            CritiqueEvent(
                as_of_date=date(2026, 4, 20),
                outcome_pct=4.2,
                old_confidence=70,
                new_confidence=72,
                rationale="x",
                source="self_critique",
            )
        ],
        field_locks={"confidence": True},
    )
    dumped = belief.model_dump(mode="json")
    rehydrated = Belief.model_validate(dumped)
    assert rehydrated == belief


def test_rationale_max_length_dos_guard() -> None:
    """Test 9 (Shared Pattern F DoS guard): rationale > 2000 chars rejected."""
    with pytest.raises(ValidationError):
        CritiqueEvent(
            as_of_date=date(2026, 4, 20),
            outcome_pct=4.2,
            old_confidence=70,
            new_confidence=72,
            rationale="a" * 2001,
            source="self_critique",
        )
    # Exactly 2000 should pass
    CritiqueEvent(
        as_of_date=date(2026, 4, 20),
        outcome_pct=4.2,
        old_confidence=70,
        new_confidence=72,
        rationale="a" * 2000,
        source="self_critique",
    )


def test_thesis_max_length_dos_guard() -> None:
    """Bonus: thesis > 10_000 chars rejected."""
    with pytest.raises(ValidationError):
        Belief.model_validate(
            {**_valid_belief_kwargs(), "thesis": "a" * 10_001}
        )


def test_ticker_length_bounds() -> None:
    """Bonus: ticker must be 1..10 chars."""
    with pytest.raises(ValidationError):
        Belief.model_validate({**_valid_belief_kwargs(), "ticker": ""})
    with pytest.raises(ValidationError):
        Belief.model_validate(
            {**_valid_belief_kwargs(), "ticker": "A" * 11}
        )


def test_version_minimum() -> None:
    """Bonus: version must be >=1 (belief exists from first write)."""
    with pytest.raises(ValidationError):
        Belief.model_validate({**_valid_belief_kwargs(), "version": 0})
