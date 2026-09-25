"""Phase 11 T1 -- MtmPolicy schema, loader, bucket lookup, and SHA (11-SPEC section 1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_hedge_fund.mtm.policy import (
    DEFAULT_MTM_POLICY_PATH,
    MtmPolicy,
    compute_mtm_policy_sha,
    load_mtm_policy,
)

BUCKETS = [
    {"name": "low", "min": 0, "max": 49},
    {"name": "medium", "min": 50, "max": 74},
    {"name": "high", "min": 75, "max": 100},
]
VALID = {
    "conviction_buckets": BUCKETS,
    "sentiment_threshold": 0.2,
    "stance_rule_version": 1,
    "market_close_buffer_minutes": 30,
}


def _policy(**overrides: object) -> MtmPolicy:
    return MtmPolicy(**{**VALID, **overrides})


def test_shipped_config_loads() -> None:
    p = load_mtm_policy(DEFAULT_MTM_POLICY_PATH)
    assert [b.name for b in p.conviction_buckets] == ["low", "medium", "high"]
    assert p.sentiment_threshold == 0.2
    assert p.stance_rule_version == 1
    assert p.market_close_buffer_minutes == 30


def test_extra_keys_forbidden() -> None:
    with pytest.raises(ValidationError):
        _policy(surprise=1)


def test_extra_bucket_keys_forbidden() -> None:
    with pytest.raises(ValidationError):
        _policy(conviction_buckets=[{**BUCKETS[0], "max": 100, "colour": "red"}])


def test_frozen() -> None:
    p = _policy()
    with pytest.raises(ValidationError):
        p.sentiment_threshold = 0.5  # type: ignore[misc]


@pytest.mark.parametrize(
    "bad",
    [
        {"sentiment_threshold": 0},
        {"sentiment_threshold": 1},
        {"stance_rule_version": 0},
        {"stance_rule_version": 1.0},  # strict int
        {"market_close_buffer_minutes": -1},
        {"market_close_buffer_minutes": 241},
        {"conviction_buckets": []},
    ],
    ids=lambda d: "+".join(f"{k}={v}" for k, v in d.items()),
)
def test_rejects_invalid_scalars(bad: dict) -> None:
    with pytest.raises(ValidationError):
        _policy(**bad)


@pytest.mark.parametrize(
    ("buckets", "fragment"),
    [
        # gap: 50 belongs to no bucket
        ([{"name": "a", "min": 0, "max": 49}, {"name": "b", "min": 51, "max": 100}], "b"),
        # overlap: 49 belongs to both
        ([{"name": "a", "min": 0, "max": 49}, {"name": "b", "min": 49, "max": 100}], "b"),
        # does not start at 0
        ([{"name": "a", "min": 1, "max": 100}], "a"),
        # does not reach 100
        ([{"name": "a", "min": 0, "max": 99}], "a"),
        # inverted
        ([{"name": "a", "min": 0, "max": 60}, {"name": "b", "min": 61, "max": 40}], "b"),
        # out of order
        ([{"name": "b", "min": 50, "max": 100}, {"name": "a", "min": 0, "max": 49}], "b"),
        # duplicate names
        ([{"name": "a", "min": 0, "max": 49}, {"name": "a", "min": 50, "max": 100}], "a"),
    ],
    ids=["gap", "overlap", "not-from-0", "not-to-100", "inverted", "unsorted", "dup-name"],
)
def test_gap_or_overlap_rejected(buckets: list[dict], fragment: str) -> None:
    """11-PREMORTEM #27: every conviction 0..100 maps to exactly one bucket."""
    with pytest.raises(ValidationError, match=f"'{fragment}'"):
        _policy(conviction_buckets=buckets)


@pytest.mark.parametrize(
    ("conviction", "bucket"),
    [(0, "low"), (49, "low"), (50, "medium"), (74, "medium"), (75, "high"), (100, "high")],
)
def test_boundaries_map_to_one_bucket(conviction: int, bucket: str) -> None:
    """11-PREMORTEM #27."""
    assert _policy().bucket_for(conviction) == bucket


@pytest.mark.parametrize("bad", [-1, 101])
def test_bucket_for_out_of_range_raises(bad: int) -> None:
    with pytest.raises(ValueError, match=str(bad)):
        _policy().bucket_for(bad)


def test_sha_deterministic() -> None:
    a = compute_mtm_policy_sha(_policy())
    assert a == compute_mtm_policy_sha(_policy())
    assert len(a) == 64


@pytest.mark.parametrize(
    "change",
    [
        {"sentiment_threshold": 0.25},
        {"stance_rule_version": 2},
        {"market_close_buffer_minutes": 45},
        {"conviction_buckets": [{**BUCKETS[0], "max": 59}, {**BUCKETS[1], "min": 60}, BUCKETS[2]]},
        {"conviction_buckets": [{**BUCKETS[0], "name": "lo"}, BUCKETS[1], BUCKETS[2]]},
    ],
    ids=["threshold", "rule-version", "buffer", "bucket-bounds", "bucket-name"],
)
def test_sha_changes_per_field(change: dict) -> None:
    """11-PREMORTEM #28: every field moves the SHA."""
    assert compute_mtm_policy_sha(_policy(**change)) != compute_mtm_policy_sha(_policy())


def test_loader_rejects_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "p.yaml"
    bad.write_text("sentiment_threshold: 0.2\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_mtm_policy(bad)
