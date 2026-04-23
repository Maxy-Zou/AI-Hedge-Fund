"""Phase-8 human-review subsystem.

Mirrors ``src/ai_hedge_fund/risk/`` -- ``ReviewPolicy`` is the configurable
gate; ``ReviewDecision`` is the audit record; ``compute_review_policy_sha``
is the policy fingerprint (T-08-02). Plans 08-03 and 08-04 consume these
primitives as black-box contracts via
``from ai_hedge_fund.review import ...``.

Threat mitigations (see ``08-01-PLAN.md::threat_model``):
    T-08-01: Tampering / unknown-key drift -- ``load_review_policy`` uses
             ``yaml.safe_load`` exclusively; ``ReviewPolicy`` uses
             ``ConfigDict(extra="forbid")``.
    T-08-02: Policy drift without audit -- ``compute_review_policy_sha``
             produces a deterministic SHA-256 over canonical-JSON dump.
    T-08-13: Spoofed ``ReviewDecision`` -- ``ReviewDecision.model_validate``
             enforces Literal status + 64-char sha + non-empty reviewer
             fields + ``extra="forbid"``.
"""

from __future__ import annotations

from ai_hedge_fund.review.decision import ReviewDecision
from ai_hedge_fund.review.policy import (
    DEFAULT_REVIEW_POLICY_PATH,
    ReviewPolicy,
    compute_review_policy_sha,
    load_review_policy,
)

__all__ = [
    "DEFAULT_REVIEW_POLICY_PATH",
    "ReviewDecision",
    "ReviewPolicy",
    "compute_review_policy_sha",
    "load_review_policy",
]
