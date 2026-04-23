"""Plan 08-01 Task 1: ReviewPolicy + load + sha tests.

Verifies T-08-01 (YAML tampering / unknown-key drift) and T-08-02 (policy
drift without audit) mitigations:
- ``yaml.safe_load`` is used (never ``yaml.load``)
- ``ConfigDict(extra="forbid")`` rejects unknown keys
- ``Field(ge=..., le=...)`` rejects out-of-range values
- ``compute_review_policy_sha`` is deterministic, stable, and change-sensitive
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_hedge_fund.review.policy import (
    ReviewPolicy,
    compute_review_policy_sha,
    load_review_policy,
)


def test_default_policy_threshold_is_70() -> None:
    """Test 3 (defaults): ReviewPolicy() constructs with threshold=70, reviewer_id_default=None."""
    p = ReviewPolicy()
    assert p.conviction_threshold == 70
    assert p.reviewer_id_default is None


def test_load_from_valid_yaml(review_policy_sample_path: Path) -> None:
    """Test 2: load(valid_yaml) returns ReviewPolicy(threshold=70, reviewer='test')."""
    p = load_review_policy(review_policy_sample_path)
    assert p.conviction_threshold == 70
    assert p.reviewer_id_default == "test"


def test_malformed_yaml_rejects_extra_key(review_policy_malformed_path: Path) -> None:
    """Test 1 (extra='forbid'): load rejects YAML with unknown keys."""
    with pytest.raises(ValidationError, match="unknown_key|Extra inputs"):
        load_review_policy(review_policy_malformed_path)


def test_threshold_out_of_range_rejected() -> None:
    """Test 4: threshold < 0 or > 100 raises ValidationError."""
    with pytest.raises(ValidationError):
        ReviewPolicy(conviction_threshold=-1)
    with pytest.raises(ValidationError):
        ReviewPolicy(conviction_threshold=101)


def test_policy_is_frozen() -> None:
    """Test 5: assignment to an instance attribute raises (frozen=True)."""
    p = ReviewPolicy()
    with pytest.raises(ValidationError):
        p.conviction_threshold = 80  # type: ignore[misc]


def test_sha_is_deterministic() -> None:
    """Test 6: compute_review_policy_sha is stable across repeated calls for the same policy."""
    p = ReviewPolicy()
    assert compute_review_policy_sha(p) == compute_review_policy_sha(p)


SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def test_sha_is_64_lowercase_hex() -> None:
    """Test 7: SHA output matches ^[0-9a-f]{64}$."""
    sha = compute_review_policy_sha(ReviewPolicy())
    assert SHA_RE.fullmatch(sha)


def test_sha_is_change_sensitive() -> None:
    """Test 8: one-field delta yields a different SHA (three-way identity)."""
    a = ReviewPolicy(conviction_threshold=70)
    b = ReviewPolicy(conviction_threshold=71)
    # same policy -> same sha
    assert compute_review_policy_sha(a) == compute_review_policy_sha(a)
    # one-field delta -> different sha
    assert compute_review_policy_sha(a) != compute_review_policy_sha(b)
    # revert -> idempotent
    a_again = ReviewPolicy(conviction_threshold=70)
    assert compute_review_policy_sha(a) == compute_review_policy_sha(a_again)


def test_policy_module_uses_safe_load_only() -> None:
    """Test 9: T-08-01 defense-in-depth: the loader source never calls yaml.load()."""
    src = Path("src/ai_hedge_fund/review/policy.py").read_text()
    assert "yaml.safe_load" in src
    assert "yaml.load(" not in src


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    """Test 10: load_review_policy(nonexistent) raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_review_policy(tmp_path / "nonexistent.yaml")
