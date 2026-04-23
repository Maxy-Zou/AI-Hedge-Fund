"""Shared fixtures for Phase-8 review tests.

Mirrors tests/risk/conftest.py (Phase-6 risk fixture layout). Plan 08-01
imports these fixtures via tests/integration/conftest.py re-export shim.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def review_policy_sample_path(tmp_path: Path) -> Path:
    """Copy the sample YAML into a tmp_path so tests can mutate without polluting fixtures."""
    src = FIXTURES_DIR / "review_policy_sample.yaml"
    dst = tmp_path / "review_policy.yaml"
    shutil.copy(src, dst)
    return dst


@pytest.fixture
def review_policy_malformed_path(tmp_path: Path) -> Path:
    """Path to the malformed YAML for extra='forbid' regression tests."""
    src = FIXTURES_DIR / "review_policy_malformed.yaml"
    dst = tmp_path / "review_policy_malformed.yaml"
    shutil.copy(src, dst)
    return dst


@pytest.fixture
def review_policy(review_policy_sample_path: Path):
    """Pre-loaded ReviewPolicy instance (lazy import -- Plan 08-01 defines the class)."""
    from ai_hedge_fund.review.policy import load_review_policy

    return load_review_policy(review_policy_sample_path)
