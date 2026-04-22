"""Risk policy schema (Pydantic) + YAML loader + SHA-256 fingerprint.

Single source of truth for the risk limits governing the paper portfolio.
The policy is loaded from a human-editable YAML file at pipeline startup,
validated via Pydantic (``extra="forbid"`` so unknown keys raise early), and
fingerprinted with SHA-256 so every ``RiskAssessment`` records the exact
policy version that produced it (T-06-04 audit mitigation).

Threat mitigations:
    T-06-01: Tampering / unknown-key drift -- ``load_policy`` uses
             ``yaml.safe_load`` exclusively (never ``yaml.load`` which can
             instantiate arbitrary Python objects). ``RiskPolicy`` uses
             ``ConfigDict(extra="forbid")`` so silent additional keys raise
             ``ValidationError`` before the pipeline runs.
    T-06-04: Policy drift without audit -- ``compute_policy_sha`` is
             deterministic: canonical-JSON (``sort_keys=True``, compact
             separators) SHA-256, identical bytes for identical policy.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_POLICY_PATH: Path = Path("config/risk_policy.yaml")


class RiskPolicy(BaseModel):
    """Human-editable risk limits for the paper portfolio.

    All percentage fields are expressed as raw percent (e.g., ``10.0`` means
    10%); correlation bounds are expressed as fractions in ``[0.0, 1.0]``.
    Frozen + ``extra="forbid"`` so policy instances are immutable and unknown
    YAML keys surface as ``ValidationError`` (T-06-01).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Hard caps (percent of portfolio)
    max_single_position_pct: float = Field(
        ge=0.0,
        le=100.0,
        description="Hard cap on any one position as percent of portfolio",
    )
    max_sector_pct: float = Field(
        ge=0.0,
        le=100.0,
        description="Hard cap on any one sector as percent of portfolio",
    )
    max_total_exposure_pct: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="Sum of all long exposure; paper-portfolio v1 is long-only",
    )

    # Correlation
    max_correlation_with_portfolio: float = Field(
        ge=0.0,
        le=1.0,
        description="Max Pearson correlation with any existing position",
    )
    correlation_window_days: int = Field(
        default=60,
        ge=20,
        le=504,
        description="Trading-day window used for the correlation check",
    )

    # Drawdown
    max_projected_drawdown_pct: float = Field(
        ge=0.0,
        le=100.0,
        description="Historical-simulation max drawdown cap (percent)",
    )
    drawdown_window_days: int = Field(
        default=252,
        ge=60,
        le=504,
        description="Trading-day window used for the drawdown projection",
    )
    min_history_days: int = Field(
        default=60,
        ge=20,
        le=504,
        description="Minimum price-history days required to evaluate a candidate",
    )

    # Exclusions
    excluded_instrument_types: list[str] = Field(
        default_factory=list,
        description="Instrument types that cannot enter the portfolio (e.g., OTC, SPAC)",
    )
    excluded_sectors: list[str] = Field(
        default_factory=list,
        description="Full sector names that cannot enter the portfolio",
    )

    # Conviction -> candidate position size multipliers (applied to max_single_position_pct).
    # Upper bound is 2.0 so operators can opt-in to over-sizing for high-conviction
    # signals; values above 1.0 intentionally allow the derived size to exceed
    # max_single_position_pct so check_position_size can veto (RISK-02 regression
    # test). Default multipliers (1.0 / 0.5 / 0.25) keep the derived size at or
    # below the cap.
    size_high_conviction_multiplier: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Multiplier on max_single_position_pct for high-conviction signals",
    )
    size_medium_conviction_multiplier: float = Field(
        default=0.5,
        ge=0.0,
        le=2.0,
        description="Multiplier on max_single_position_pct for medium-conviction signals",
    )
    size_low_conviction_multiplier: float = Field(
        default=0.25,
        ge=0.0,
        le=2.0,
        description="Multiplier on max_single_position_pct for low-conviction signals",
    )


def load_policy(path: Path | str = DEFAULT_POLICY_PATH) -> RiskPolicy:
    """Load and validate a ``RiskPolicy`` from a YAML file.

    Uses ``yaml.safe_load`` exclusively (T-06-01). ``RiskPolicy`` validates
    on construction: unknown keys raise ``ValidationError`` and out-of-range
    values raise ``ValidationError``.

    Args:
        path: Path to the YAML file. Defaults to ``config/risk_policy.yaml``.

    Returns:
        Validated ``RiskPolicy`` instance.

    Raises:
        FileNotFoundError: The file does not exist.
        pydantic.ValidationError: The YAML is not a valid ``RiskPolicy``.
    """
    text = Path(path).read_text()
    data = yaml.safe_load(text)
    return RiskPolicy.model_validate(data)


def compute_policy_sha(policy: RiskPolicy) -> str:
    """Return the SHA-256 fingerprint of a ``RiskPolicy`` (T-06-04).

    The fingerprint is computed over the canonical-JSON dump
    (``sort_keys=True``, compact separators) of the validated policy. Two
    semantically-identical policies therefore share a fingerprint, and any
    field change -- however small -- produces a different 64-char hex.

    Args:
        policy: A validated ``RiskPolicy`` instance.

    Returns:
        Lowercase 64-character SHA-256 hex digest.
    """
    canonical = json.dumps(
        policy.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
