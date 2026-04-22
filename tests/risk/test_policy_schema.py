"""Tests for RiskPolicy schema, YAML loader, and policy SHA fingerprint.

Verifies T-06-01 (YAML tampering) and T-06-04 (policy drift audit) mitigations:
- ``yaml.safe_load`` is used (never ``yaml.load``)
- ``ConfigDict(extra="forbid")`` rejects unknown keys
- ``Field(ge=..., le=...)`` rejects out-of-range values
- ``compute_policy_sha`` is deterministic, stable, and change-sensitive
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_hedge_fund.risk.policy import RiskPolicy, compute_policy_sha, load_policy

# Defaults that mirror config/risk_policy.yaml; kept here so tests do not
# depend on the sample fixture for happy-path validation.
_DEFAULTS: dict[str, object] = {
    "max_single_position_pct": 10.0,
    "max_sector_pct": 30.0,
    "max_total_exposure_pct": 100.0,
    "max_correlation_with_portfolio": 0.80,
    "correlation_window_days": 60,
    "max_projected_drawdown_pct": 25.0,
    "drawdown_window_days": 252,
    "min_history_days": 60,
    "excluded_instrument_types": ["OTC", "SPAC"],
    "excluded_sectors": [],
    "size_high_conviction_multiplier": 1.0,
    "size_medium_conviction_multiplier": 0.5,
    "size_low_conviction_multiplier": 0.25,
}


def test_risk_policy_accepts_defaults() -> None:
    """Test 1: RiskPolicy.model_validate accepts the full defaults dict."""
    policy = RiskPolicy.model_validate(_DEFAULTS)
    assert policy.max_single_position_pct == 10.0
    assert policy.max_sector_pct == 30.0
    assert policy.max_correlation_with_portfolio == 0.80
    assert policy.correlation_window_days == 60
    assert policy.drawdown_window_days == 252
    assert policy.min_history_days == 60


def test_risk_policy_rejects_unknown_key() -> None:
    """Test 2: T-06-01 mitigation -- unknown YAML key raises ValidationError."""
    data = {**_DEFAULTS, "foo": 1}
    with pytest.raises(ValidationError):
        RiskPolicy.model_validate(data)


def test_risk_policy_rejects_out_of_range_position_pct() -> None:
    """Test 3a: max_single_position_pct=150.0 violates le=100.0."""
    data = {**_DEFAULTS, "max_single_position_pct": 150.0}
    with pytest.raises(ValidationError):
        RiskPolicy.model_validate(data)


def test_risk_policy_rejects_out_of_range_correlation() -> None:
    """Test 3b: max_correlation_with_portfolio=1.5 violates le=1.0."""
    data = {**_DEFAULTS, "max_correlation_with_portfolio": 1.5}
    with pytest.raises(ValidationError):
        RiskPolicy.model_validate(data)


def test_load_policy_returns_risk_policy(sample_policy_path: Path) -> None:
    """Test 4: load_policy returns a RiskPolicy instance from the sample YAML."""
    policy = load_policy(sample_policy_path)
    assert isinstance(policy, RiskPolicy)
    # Sample fixture uses tighter thresholds (test integration room).
    assert policy.max_single_position_pct == 8.0
    assert policy.max_sector_pct == 25.0


def test_load_policy_raises_file_not_found(tmp_path: Path) -> None:
    """Test 5: Non-existent path raises FileNotFoundError (from read_text)."""
    with pytest.raises(FileNotFoundError):
        load_policy(tmp_path / "does_not_exist.yaml")


def test_compute_policy_sha_returns_64_char_lowercase_hex() -> None:
    """Test 6: compute_policy_sha returns 64-char lowercase hex (SHA-256)."""
    policy = RiskPolicy.model_validate(_DEFAULTS)
    sha = compute_policy_sha(policy)
    assert isinstance(sha, str)
    assert len(sha) == 64
    assert sha == sha.lower()
    # Hex chars only.
    assert all(c in "0123456789abcdef" for c in sha)


def test_compute_policy_sha_is_stable() -> None:
    """Test 7: Same policy produces the same SHA across calls."""
    policy_a = RiskPolicy.model_validate(_DEFAULTS)
    policy_b = RiskPolicy.model_validate(_DEFAULTS)
    assert compute_policy_sha(policy_a) == compute_policy_sha(policy_b)
    assert compute_policy_sha(policy_a) == compute_policy_sha(policy_a)


def test_compute_policy_sha_is_change_sensitive() -> None:
    """Test 8: Changing any field changes the SHA."""
    base = RiskPolicy.model_validate(_DEFAULTS)
    tweaked_data = {**_DEFAULTS, "max_single_position_pct": 9.99}
    tweaked = RiskPolicy.model_validate(tweaked_data)
    assert compute_policy_sha(base) != compute_policy_sha(tweaked)


def test_policy_module_uses_safe_load_only() -> None:
    """Test 9: yaml.safe_load (not yaml.load) is used in the loader.

    Guards against T-06-01 YAML tampering via unsafe ``yaml.load`` (which can
    instantiate arbitrary Python objects).
    """
    import ai_hedge_fund.risk.policy as policy_mod

    source = Path(policy_mod.__file__).read_text()
    assert "yaml.safe_load" in source
    # Ensure raw ``yaml.load(`` (with paren) never appears.
    assert "yaml.load(" not in source
