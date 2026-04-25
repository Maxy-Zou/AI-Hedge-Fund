"""Plan 08-01 Task 2: FinalSignalOutput + assemble_final_signal + derive_risk_score.

Verifies:
- T-08-11 (SIG-01 schema subversion) -- every required field must be present
  and of the right shape; no nullable required fields; extra keys rejected;
  frozen.
- T-08-12 (LLM-authored risk_score) -- derive_risk_score is pure Python,
  deterministic; assemble_final_signal has zero LLM calls (tested
  end-to-end with plain state dicts). Post-fix: derive_risk_score reads
  the deterministic ``utilization`` field on the assessment (08-RESEARCH.md
  A9). Legacy fallback to observed/limit is still tested.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_hedge_fund.output.signal import assemble_final_signal, derive_risk_score
from ai_hedge_fund.schemas.signal_output import FinalSignalOutput

SHA_A = "a" * 64
SHA_B = "b" * 64


def _valid_kwargs(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ticker": "AAPL",
        "as_of_date": "2026-04-20",
        "direction": "long",
        "conviction": 75,
        "thesis_summary": "Clear bullish thesis.",
        "risk_score": 30,
        "thesis_link": "episodic://42",
        "policy_sha": SHA_A,
        "review_policy_sha": SHA_B,
        "episodic_id": 42,
        "review_status": "NOT_REQUIRED",
    }
    base.update(over)
    return base


# ---- FinalSignalOutput schema tests ----


def test_valid_construction() -> None:
    """Test 1: all 11 fields populated constructs successfully."""
    s = FinalSignalOutput(**_valid_kwargs())  # type: ignore[arg-type]
    assert s.ticker == "AAPL" and s.conviction == 75


@pytest.mark.parametrize(
    "field",
    [
        "ticker",
        "as_of_date",
        "direction",
        "conviction",
        "thesis_summary",
        "risk_score",
        "thesis_link",
        "policy_sha",
        "review_policy_sha",
        "episodic_id",
        "review_status",
    ],
)
def test_missing_any_required_field_raises(field: str) -> None:
    """Test 2: deleting any required field raises ValidationError (SIG-01 no-null contract)."""
    kwargs = _valid_kwargs()
    del kwargs[field]
    with pytest.raises(ValidationError):
        FinalSignalOutput(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [-1, 101])
def test_conviction_out_of_range(bad: int) -> None:
    """Test 3a: conviction outside [0, 100] raises."""
    with pytest.raises(ValidationError):
        FinalSignalOutput(**_valid_kwargs(conviction=bad))  # type: ignore[arg-type]


@pytest.mark.parametrize("good", [0, 100])
def test_conviction_boundaries_accepted(good: int) -> None:
    """Test 3b: conviction=0 and conviction=100 are accepted."""
    FinalSignalOutput(**_valid_kwargs(conviction=good))  # type: ignore[arg-type]


def test_direction_literal_enforced() -> None:
    """Test 4: direction outside {long, short, neutral} raises."""
    with pytest.raises(ValidationError):
        FinalSignalOutput(**_valid_kwargs(direction="up"))  # type: ignore[arg-type]


@pytest.mark.parametrize("good", ["long", "short", "neutral"])
def test_direction_literal_accepts_valid(good: str) -> None:
    """Test 4b: each of {long, short, neutral} is accepted."""
    FinalSignalOutput(**_valid_kwargs(direction=good))  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [-1, 101])
def test_risk_score_out_of_range(bad: int) -> None:
    """Test 5: risk_score outside [0, 100] raises."""
    with pytest.raises(ValidationError):
        FinalSignalOutput(**_valid_kwargs(risk_score=bad))  # type: ignore[arg-type]


def test_review_status_literal_enforced() -> None:
    """Test 6: review_status outside {NOT_REQUIRED, APPROVED, REJECTED} raises."""
    with pytest.raises(ValidationError):
        FinalSignalOutput(**_valid_kwargs(review_status="PENDING"))  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["policy_sha", "review_policy_sha"])
@pytest.mark.parametrize("bad", ["a" * 63, "a" * 65])
def test_sha_length_enforced(field: str, bad: str) -> None:
    """Test 7: policy_sha + review_policy_sha must be exactly 64 chars."""
    with pytest.raises(ValidationError):
        FinalSignalOutput(**_valid_kwargs(**{field: bad}))  # type: ignore[arg-type]


def test_as_of_date_length_enforced() -> None:
    """Test 8: as_of_date must be exactly 10 chars."""
    with pytest.raises(ValidationError):
        FinalSignalOutput(**_valid_kwargs(as_of_date="2026-4-1"))  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "A" * 11])
def test_ticker_bounds(bad: str) -> None:
    """Test 9: ticker min_length=1, max_length=10."""
    with pytest.raises(ValidationError):
        FinalSignalOutput(**_valid_kwargs(ticker=bad))  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "x" * 2001])
def test_thesis_summary_bounds(bad: str) -> None:
    """Test 10: thesis_summary min_length=1, max_length=2000."""
    with pytest.raises(ValidationError):
        FinalSignalOutput(**_valid_kwargs(thesis_summary=bad))  # type: ignore[arg-type]


def test_episodic_id_ge_1() -> None:
    """Test 11: episodic_id must be >= 1."""
    with pytest.raises(ValidationError):
        FinalSignalOutput(**_valid_kwargs(episodic_id=0))  # type: ignore[arg-type]


def test_extra_key_forbidden() -> None:
    """Test 12: unknown kwarg raises (extra='forbid')."""
    with pytest.raises(ValidationError):
        FinalSignalOutput(**_valid_kwargs(unknown="x"))  # type: ignore[arg-type]


def test_frozen() -> None:
    """Test 13: setattr raises (frozen=True)."""
    s = FinalSignalOutput(**_valid_kwargs())  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        s.ticker = "MSFT"  # type: ignore[misc]


def test_json_round_trip() -> None:
    """Test 14: model_dump(mode='json') + model_validate returns equal instance."""
    s = FinalSignalOutput(**_valid_kwargs())  # type: ignore[arg-type]
    data = s.model_dump(mode="json")
    s2 = FinalSignalOutput.model_validate(data)
    assert s == s2


# ---- assemble_final_signal tests ----


def _realistic_state(
    conviction: int = 75,
    status: str = "APPROVED",
    utilization: float | None = 0.5,
) -> dict:
    risk: dict[str, object] = {
        "status": status,
        "policy_sha": SHA_A,
        "observed": 4.0,
        "limit": 8.0,
    }
    if utilization is not None:
        risk["utilization"] = utilization
    return {
        "ticker": "AAPL",
        "as_of_date": "2026-04-20",
        "signal": {"direction": "long", "thesis_summary": "Bullish on iPhone cycle."},
        "thesis": {"confidence": conviction},
        "risk_assessment": risk,
    }


def test_assembler_happy_path() -> None:
    """Test 15: realistic state + args produce a valid FinalSignalOutput."""
    out = assemble_final_signal(
        _realistic_state(),
        review_policy_sha=SHA_B,
        episodic_id=42,
    )
    assert out.review_status == "NOT_REQUIRED"
    assert out.conviction == 75
    assert out.thesis_link == "episodic://42"
    assert out.direction == "long"
    assert out.policy_sha == SHA_A
    assert out.review_policy_sha == SHA_B


def test_assembler_vetoed_risk_score_100() -> None:
    """Test 16: VETOED risk_assessment -> risk_score == 100."""
    out = assemble_final_signal(
        _realistic_state(status="VETOED", utilization=1.0),
        review_policy_sha=SHA_B,
        episodic_id=42,
    )
    assert out.risk_score == 100


def test_assembler_review_status_override() -> None:
    """Test 17: review_status kwarg overrides the NOT_REQUIRED default."""
    out = assemble_final_signal(
        _realistic_state(),
        review_policy_sha=SHA_B,
        episodic_id=42,
        review_status="APPROVED",
    )
    assert out.review_status == "APPROVED"


def test_assembler_thesis_link_format() -> None:
    """Test 18: thesis_link == f'episodic://{episodic_id}'."""
    out = assemble_final_signal(
        _realistic_state(),
        review_policy_sha=SHA_B,
        episodic_id=99,
    )
    assert out.thesis_link == "episodic://99"


def test_assembler_conviction_from_thesis_confidence() -> None:
    """Test 19: conviction is read from state['thesis']['confidence']."""
    out = assemble_final_signal(
        _realistic_state(conviction=85),
        review_policy_sha=SHA_B,
        episodic_id=42,
    )
    assert out.conviction == 85


def test_assembler_uses_utilization_field_for_risk_score() -> None:
    """Regression: APPROVED with utilization=0.42 -> risk_score == 42.

    Pre-fix bug: derive_risk_score read observed/limit (None on APPROVED)
    and produced 0. Post-fix: it reads utilization, which the node always
    sets.
    """
    out = assemble_final_signal(
        _realistic_state(status="APPROVED", utilization=0.42),
        review_policy_sha=SHA_B,
        episodic_id=42,
    )
    assert out.risk_score == 42


# ---- derive_risk_score tests ----


def test_derive_risk_score_vetoed_is_100() -> None:
    """Test 20: VETOED status -> 100."""
    assert derive_risk_score({"status": "VETOED"}) == 100


def test_derive_risk_score_approved_uses_utilization() -> None:
    """Test 21: APPROVED with utilization=0.5 -> 50.

    Post-fix: utilization is the canonical signal. observed/limit may be
    populated as audit metadata but no longer drive the score on the
    APPROVED path.
    """
    assert (
        derive_risk_score({"status": "APPROVED", "utilization": 0.5, "observed": 4.0, "limit": 8.0})
        == 50
    )


def test_derive_risk_score_approved_utilization_at_one_is_100() -> None:
    """Test 22: APPROVED with utilization == 1.0 -> 100 (right at the cap)."""
    assert derive_risk_score({"status": "APPROVED", "utilization": 1.0}) == 100


def test_derive_risk_score_approved_zero_utilization_is_0() -> None:
    """Test 22b: APPROVED with utilization == 0.0 -> 0."""
    assert derive_risk_score({"status": "APPROVED", "utilization": 0.0}) == 0


def test_derive_risk_score_legacy_fallback_to_observed_limit() -> None:
    """Test 23: legacy assessments without utilization fall back to
    observed/limit so older payloads in the audit trail keep working.
    """
    assert derive_risk_score({"status": "APPROVED", "observed": 4.0, "limit": 8.0}) == 50


def test_derive_risk_score_approved_empty_is_0() -> None:
    """Test 23b: APPROVED with neither utilization nor observed/limit -> 0."""
    assert derive_risk_score({"status": "APPROVED"}) == 0


def test_derive_risk_score_unknown_is_50() -> None:
    """Test 24: unknown status -> 50."""
    assert derive_risk_score({"status": "REVIEWED"}) == 50


@pytest.mark.parametrize("utilization", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_derive_risk_score_utilization_bounded(utilization: float) -> None:
    """Test 25: utilization in [0, 1] always maps into [0, 100]."""
    score = derive_risk_score({"status": "APPROVED", "utilization": utilization})
    assert 0 <= score <= 100


@pytest.mark.parametrize("observed,limit", [(0, 1), (5, 10), (100, 1), (1, 100), (-5, 10)])
def test_derive_risk_score_bounded_via_legacy_path(observed: float, limit: float) -> None:
    """Test 25b: legacy observed/limit input is always clamped to [0, 100]."""
    score = derive_risk_score({"status": "APPROVED", "observed": observed, "limit": limit})
    assert 0 <= score <= 100


def test_derive_risk_score_clamps_out_of_range_utilization() -> None:
    """Defensive: a stale payload with utilization > 1 should still clamp."""
    assert derive_risk_score({"status": "APPROVED", "utilization": 1.5}) == 100


def test_derive_risk_score_clamps_negative_utilization() -> None:
    """Defensive: a stale payload with utilization < 0 should clamp to 0."""
    assert derive_risk_score({"status": "APPROVED", "utilization": -0.25}) == 0
