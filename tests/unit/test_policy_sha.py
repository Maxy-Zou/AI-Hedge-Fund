"""Unit tests for ai_hedge_fund.policy_sha.fingerprint.

The canonical-JSON SHA-256 helper shared by risk, review, and (Phase 10)
execution policies. Promoted from two byte-identical private copies
(risk/policy.py, review/policy.py) so a third is not written for execution.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

from ai_hedge_fund.policy_sha import fingerprint


class _Model(BaseModel):
    a: int
    b: str
    c: list[int]


def _manual(model: BaseModel) -> str:
    canonical = json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_matches_canonical_json_sha256() -> None:
    m = _Model(a=1, b="x", c=[3, 2, 1])
    assert fingerprint(m) == _manual(m)


def test_is_64_char_lowercase_hex() -> None:
    fp = fingerprint(_Model(a=1, b="x", c=[]))
    assert len(fp) == 64 and fp == fp.lower()
    int(fp, 16)  # parses as hex


def test_deterministic_same_input_same_output() -> None:
    a, b = _Model(a=1, b="y", c=[1]), _Model(a=1, b="y", c=[1])
    assert fingerprint(a) == fingerprint(b)


def test_key_order_does_not_matter() -> None:
    """Canonical (sort_keys) means declaration order is irrelevant to the digest."""

    class Ab(BaseModel):
        a: int
        b: int

    class Ba(BaseModel):
        b: int
        a: int

    assert fingerprint(Ab(a=1, b=2)) == fingerprint(Ba(b=2, a=1))


def test_change_sensitive() -> None:
    assert fingerprint(_Model(a=1, b="x", c=[1])) != fingerprint(_Model(a=2, b="x", c=[1]))
