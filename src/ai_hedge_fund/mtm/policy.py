"""Mark-to-market policy: conviction buckets and attribution rules (Phase 11, 11-SPEC s1).

Human-editable YAML, validated at load (``extra="forbid"``), fingerprinted with
the shared canonical-JSON SHA-256 so every ``paper_pnl_daily`` row records the
exact rules that attributed it. Buckets must partition 0..100 with no gap or
overlap, so any conviction maps to exactly one bucket (11-PREMORTEM #27).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_hedge_fund.policy_sha import fingerprint

DEFAULT_MTM_POLICY_PATH = Path("config/mtm_policy.yaml")

_CONVICTION_MIN = 0
_CONVICTION_MAX = 100


class ConvictionBucket(BaseModel):
    """One inclusive conviction range, e.g. ``medium`` = 50..74."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=16)
    min: int = Field(ge=_CONVICTION_MIN, le=_CONVICTION_MAX, strict=True)
    max: int = Field(ge=_CONVICTION_MIN, le=_CONVICTION_MAX, strict=True)


class MtmPolicy(BaseModel):
    """Validated mark-to-market policy. Frozen; unknown keys rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conviction_buckets: tuple[ConvictionBucket, ...] = Field(min_length=1)
    sentiment_threshold: float = Field(gt=0, lt=1, description="A2: |composite| for a stance")
    stance_rule_version: int = Field(ge=1, strict=True, description="Bump when A2 rule changes")
    market_close_buffer_minutes: int = Field(ge=0, le=240, strict=True, description="D6 guard")

    @model_validator(mode="after")
    def _buckets_partition_range(self) -> MtmPolicy:
        names: set[str] = set()
        expected_min = _CONVICTION_MIN
        for bucket in self.conviction_buckets:
            if bucket.name in names:
                raise ValueError(f"duplicate conviction bucket name '{bucket.name}'")
            names.add(bucket.name)
            if bucket.min != expected_min:
                raise ValueError(
                    f"conviction bucket '{bucket.name}' must start at {expected_min} "
                    f"(got {bucket.min}); buckets must be sorted with no gap or overlap"
                )
            if bucket.max < bucket.min:
                raise ValueError(f"conviction bucket '{bucket.name}' has max < min")
            expected_min = bucket.max + 1
        last = self.conviction_buckets[-1]
        if last.max != _CONVICTION_MAX:
            raise ValueError(f"conviction bucket '{last.name}' must end at {_CONVICTION_MAX}")
        return self

    def bucket_for(self, conviction: int) -> str:
        """Name of the single bucket containing ``conviction`` (0..100 inclusive)."""
        for bucket in self.conviction_buckets:
            if bucket.min <= conviction <= bucket.max:
                return bucket.name
        raise ValueError(f"conviction {conviction} outside {_CONVICTION_MIN}..{_CONVICTION_MAX}")


def load_mtm_policy(path: Path | str = DEFAULT_MTM_POLICY_PATH) -> MtmPolicy:
    """Load and validate an :class:`MtmPolicy` from YAML (``yaml.safe_load`` only)."""
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return MtmPolicy.model_validate(data)


def compute_mtm_policy_sha(policy: MtmPolicy) -> str:
    """Canonical-JSON SHA-256 of the policy (shared helper; matches risk/review/execution)."""
    return fingerprint(policy)
