"""Phase 10 T2 -- ExecutionPolicy schema, loader, and SHA (D5, D6, D7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_hedge_fund.execution.policy import (
    DEFAULT_EXECUTION_POLICY_PATH,
    ExecutionPolicy,
    compute_execution_policy_sha,
    load_execution_policy,
)

VALID = {
    "nav_cents": 10_000_000,
    "max_position_pct": 0.05,
    "min_conviction": 55,
    "full_conviction": 90,
    "long_only": True,
    "max_attempts": 3,
    "order_type": "market",
    "limit_offset_bps": 25,
}


def test_defaults_match_signed_off_decisions() -> None:
    """D6 NAV default $100k; D7 long_only default true."""
    p = ExecutionPolicy(**VALID)
    assert p.nav_cents == 10_000_000  # $100,000
    assert p.long_only is True
    assert p.max_attempts == 3


def test_extra_keys_forbidden() -> None:
    with pytest.raises(ValidationError):
        ExecutionPolicy(**VALID, surprise=1)


def test_frozen() -> None:
    p = ExecutionPolicy(**VALID)
    with pytest.raises(ValidationError):
        p.nav_cents = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    "bad",
    [
        {"nav_cents": 0},
        {"nav_cents": -1},
        {"nav_cents": 100.5},  # strict int
        {"max_position_pct": 0},
        {"max_position_pct": 1.5},
        {"min_conviction": -1},
        {"min_conviction": 101},
        {"full_conviction": 50},  # must be > min_conviction (55)
        {"max_attempts": 0},
        {"max_attempts": 11},
        {"order_type": "stop"},
        {"limit_offset_bps": -1},
    ],
    ids=lambda d: "+".join(f"{k}={v}" for k, v in d.items()),
)
def test_rejects_invalid(bad: dict) -> None:
    with pytest.raises(ValidationError):
        ExecutionPolicy(**{**VALID, **bad})


def test_sha_deterministic_and_change_sensitive() -> None:
    a = compute_execution_policy_sha(ExecutionPolicy(**VALID))
    b = compute_execution_policy_sha(ExecutionPolicy(**VALID))
    assert a == b and len(a) == 64
    c = compute_execution_policy_sha(ExecutionPolicy(**{**VALID, "nav_cents": 20_000_000}))
    assert c != a


def test_sha_changes_when_long_only_flips() -> None:
    """09-PREMORTEM #15: a policy field with a default must still move the SHA."""
    on = compute_execution_policy_sha(ExecutionPolicy(**{**VALID, "long_only": True}))
    off = compute_execution_policy_sha(ExecutionPolicy(**{**VALID, "long_only": False}))
    assert on != off


def test_default_yaml_loads_and_matches_defaults() -> None:
    assert Path("config/execution_policy.yaml") == DEFAULT_EXECUTION_POLICY_PATH
    policy = load_execution_policy(DEFAULT_EXECUTION_POLICY_PATH)
    assert policy.nav_cents == 10_000_000
    assert policy.long_only is True


def test_loader_rejects_unknown_key(tmp_path: Path) -> None:
    bad = tmp_path / "p.yaml"
    bad.write_text("nav_cents: 10000000\nmystery: 1\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_execution_policy(bad)
