"""Human review gating policy (Phase 8 SIG-03).

Byte-for-byte mirror of ``src/ai_hedge_fund/risk/policy.py``. Loaded once at
pipeline build; immutable (``frozen=True``); ``extra="forbid"`` rejects
unknown keys (T-08-01). SHA-256 canonical-JSON fingerprint stamps every
persisted ``ReviewDecision`` (T-08-02).

Threat mitigations (see ``08-01-PLAN.md::threat_model``):
    T-08-01: Tampering / unknown-key drift -- ``load_review_policy`` uses
             ``yaml.safe_load`` exclusively (never ``yaml.load`` which can
             instantiate arbitrary Python objects). ``ReviewPolicy`` uses
             ``ConfigDict(extra="forbid")`` so unknown keys surface as
             ``ValidationError`` before the pipeline runs.
    T-08-02: Policy drift without audit -- ``compute_review_policy_sha`` is
             deterministic: canonical-JSON (``sort_keys=True``, compact
             separators) SHA-256, identical bytes for identical policy.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_REVIEW_POLICY_PATH: Path = Path("config/review_policy.yaml")


class ReviewPolicy(BaseModel):
    """Human-editable review gating rules.

    Frozen + ``extra="forbid"``: policy instances are immutable; unknown YAML
    keys surface as ``ValidationError`` (T-08-01).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    conviction_threshold: int = Field(
        ge=0,
        le=100,
        default=70,
        description="Signals with conviction >= this value require human review",
    )
    review_prompt_template: str = Field(
        default=("Review required: {ticker} conviction {conviction}. Approve (y) or reject (n)?"),
        min_length=1,
        description="stdin prompt shown to the CLI reviewer",
    )
    reviewer_id_default: str | None = Field(
        default=None,
        description="Optional default reviewer id (falls back to OS user on CLI)",
    )


def load_review_policy(path: Path | str = DEFAULT_REVIEW_POLICY_PATH) -> ReviewPolicy:
    """Load and validate a ``ReviewPolicy`` from a YAML file.

    Uses ``yaml.safe_load`` exclusively (T-08-01 -- ``yaml.load`` is forbidden
    because it can instantiate arbitrary Python objects via YAML tags).
    ``ReviewPolicy`` validates on construction: unknown keys raise
    ``ValidationError`` and out-of-range values raise ``ValidationError``.

    Args:
        path: Path to the YAML file. Defaults to ``config/review_policy.yaml``.

    Returns:
        Validated ``ReviewPolicy`` instance.

    Raises:
        FileNotFoundError: The file does not exist.
        pydantic.ValidationError: The YAML is not a valid ``ReviewPolicy``.
    """
    text = Path(path).read_text()
    data = yaml.safe_load(text)
    return ReviewPolicy.model_validate(data)


def compute_review_policy_sha(policy: ReviewPolicy) -> str:
    """Return the SHA-256 fingerprint of a ``ReviewPolicy`` (T-08-02).

    The fingerprint is computed over the canonical-JSON dump
    (``sort_keys=True``, compact separators) of the validated policy. Two
    semantically-identical policies share a fingerprint, and any field change
    -- however small -- produces a different 64-char hex.

    Args:
        policy: A validated ``ReviewPolicy`` instance.

    Returns:
        Lowercase 64-character SHA-256 hex digest.
    """
    canonical = json.dumps(
        policy.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
