"""Execution policy: deterministic sizing + submission rules (Phase 10, D5).

Human-editable YAML, validated at load (``extra="forbid"``), fingerprinted with
the shared canonical-JSON SHA-256 so every paper trade records the exact policy
bytes that sized it. NAV is configurable with a $100,000 default (D6); trading
is long-only by default (D7). Both are auditable: editing either changes the SHA.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_hedge_fund.policy_sha import fingerprint

DEFAULT_EXECUTION_POLICY_PATH = Path("config/execution_policy.yaml")


class ExecutionPolicy(BaseModel):
    """Validated execution/sizing policy. Frozen; unknown keys rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nav_cents: int = Field(gt=0, strict=True, description="Paper NAV in cents (D6, default $100k)")
    max_position_pct: float = Field(gt=0, le=1, description="Cap per position as fraction of NAV")
    min_conviction: int = Field(ge=0, le=100, description="Below this, size scale is 0 (refuse)")
    full_conviction: int = Field(ge=0, le=100, description="At/above this, size scale is 1.0")
    long_only: bool = Field(default=True, description="D7: short signals refused when true")
    max_attempts: int = Field(ge=1, le=10, strict=True, description="Cap on submit attempts/signal")
    order_type: Literal["market", "limit"] = "market"
    limit_offset_bps: int = Field(ge=0, le=1000, strict=True, default=25)

    @model_validator(mode="after")
    def _full_above_min(self) -> ExecutionPolicy:
        if self.full_conviction <= self.min_conviction:
            raise ValueError("full_conviction must be greater than min_conviction")
        return self


def load_execution_policy(path: Path | str = DEFAULT_EXECUTION_POLICY_PATH) -> ExecutionPolicy:
    """Load and validate an :class:`ExecutionPolicy` from YAML (``yaml.safe_load`` only)."""
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return ExecutionPolicy.model_validate(data)


def compute_execution_policy_sha(policy: ExecutionPolicy) -> str:
    """Canonical-JSON SHA-256 of the policy (shared helper; matches risk/review)."""
    return fingerprint(policy)
