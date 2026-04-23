"""Plan 08-01 Task 1: ReviewDecision schema tests.

Verifies T-08-13 (spoofed review payload) mitigation:
- Literal-typed status + 64-char SHA + non-empty reviewer_id/reviewer_note all
  enforced at the Pydantic layer so malformed resume payloads fail loudly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_hedge_fund.review.decision import ReviewDecision

VALID_SHA = "a" * 64


def _valid_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "status": "APPROVED",
        "reviewer_id": "maxzou",
        "reviewer_note": "thesis holds; cleared.",
        "reviewed_at": datetime.now(UTC),
        "review_policy_sha": VALID_SHA,
    }
    base.update(overrides)
    return base


def test_valid_construction() -> None:
    """Test 1: full valid kwargs construct successfully."""
    d = ReviewDecision(**_valid_kwargs())  # type: ignore[arg-type]
    assert d.status == "APPROVED"
    assert d.review_policy_sha == VALID_SHA


def test_invalid_status_rejected() -> None:
    """Test 2: status outside {APPROVED, REJECTED} raises."""
    with pytest.raises(ValidationError):
        ReviewDecision(**_valid_kwargs(status="MAYBE"))  # type: ignore[arg-type]


def test_missing_reviewer_id_rejected() -> None:
    """Test 3: missing reviewer_id raises."""
    kwargs = _valid_kwargs()
    del kwargs["reviewer_id"]
    with pytest.raises(ValidationError):
        ReviewDecision(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["a" * 63, "a" * 65])
def test_sha_length_enforced(bad: str) -> None:
    """Test 4: review_policy_sha length must be exactly 64."""
    with pytest.raises(ValidationError):
        ReviewDecision(**_valid_kwargs(review_policy_sha=bad))  # type: ignore[arg-type]


def test_extra_key_forbidden() -> None:
    """Test 5: unknown kwarg raises (extra='forbid')."""
    with pytest.raises(ValidationError):
        ReviewDecision(**_valid_kwargs(unknown_key="x"))  # type: ignore[arg-type]


def test_frozen() -> None:
    """Test 6: mutating a field raises (frozen=True)."""
    d = ReviewDecision(**_valid_kwargs())  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        d.status = "REJECTED"  # type: ignore[misc]


@pytest.mark.parametrize("note", ["", "x" * 2001])
def test_reviewer_note_bounds(note: str) -> None:
    """Test 7: reviewer_note min_length=1, max_length=2000."""
    with pytest.raises(ValidationError):
        ReviewDecision(**_valid_kwargs(reviewer_note=note))  # type: ignore[arg-type]


def test_rejected_status_accepted() -> None:
    """Smoke: REJECTED is also a valid status."""
    d = ReviewDecision(**_valid_kwargs(status="REJECTED"))  # type: ignore[arg-type]
    assert d.status == "REJECTED"


def test_reviewer_id_bounds() -> None:
    """reviewer_id min_length=1, max_length=64."""
    with pytest.raises(ValidationError):
        ReviewDecision(**_valid_kwargs(reviewer_id=""))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ReviewDecision(**_valid_kwargs(reviewer_id="x" * 65))  # type: ignore[arg-type]
