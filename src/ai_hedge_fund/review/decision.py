"""ReviewDecision -- immutable human reviewer record (Phase 8 SIG-03).

Phase 8 parallels Phase 6 ``RiskAssessment``: frozen, ``extra="forbid"``,
append-only (persisted via ``review_store_node`` as a new
``record_type='review'`` row in Plan 08-03). The ``review_policy_sha`` field
is stamped by the CLI resumer (not the reviewer) so every persisted decision
is attributable to the exact policy version that gated it (T-08-02).

Threat mitigations:
    T-08-13: Spoofed / malformed ReviewDecision -- ``status`` Literal,
             ``review_policy_sha`` fixed at 64 chars, non-empty
             ``reviewer_id`` / ``reviewer_note``, ``extra="forbid"``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewDecision(BaseModel):
    """Human reviewer's approve/reject + note. Append-only; never mutated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["APPROVED", "REJECTED"] = Field(
        description="Deterministic outcome of human review (no middle state).",
    )
    reviewer_id: str = Field(
        min_length=1,
        max_length=64,
        description="Identifier of the human reviewer (e.g., OS username).",
    )
    reviewer_note: str = Field(
        min_length=1,
        max_length=2000,
        description="Free-form rationale explaining the approve/reject decision.",
    )
    reviewed_at: datetime = Field(
        description="UTC timestamp of the review.",
    )
    review_policy_sha: str = Field(
        min_length=64,
        max_length=64,
        description=(
            "SHA-256 hex of the ReviewPolicy that gated this decision. "
            "Mandatory for audit (T-08-02)."
        ),
    )
