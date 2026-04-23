"""ReviewDeps -- immutable deps for human_review_node + review_store_node.

Byte-for-byte mirror of :mod:`ai_hedge_fund.graph.memory_deps`. Same
XOR ``policy`` / ``policy_path`` pattern as :class:`ai_hedge_fund.graph.risk_deps.RiskDeps`.

Threat mitigations:
    T-08-22 (review-policy drift at runtime): the bundled policy is
        frozen (see :class:`ai_hedge_fund.review.policy.ReviewPolicy` which
        sets ``model_config = ConfigDict(extra="forbid", frozen=True)``).
        ``compute_review_policy_sha`` is computed once at pipeline build
        time so every persisted ``ReviewDecision`` is attributable to the
        exact policy version that gated it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing-only
    from sqlalchemy.orm import Session

    from ai_hedge_fund.review.policy import ReviewPolicy


@dataclass(frozen=True)
class ReviewDeps:
    """Immutable dependency bundle for Phase-8 graph review nodes.

    Attributes:
        db_session: SQLAlchemy session for the review-row append
            (:func:`ai_hedge_fund.graph.nodes.review_store_node`).
        policy: Pre-loaded :class:`ReviewPolicy`. Preferred -- the SHA is
            cached on the instance via module-level computation at pipeline
            build time.
        policy_path: Alternative to ``policy``; if supplied, the pipeline
            builder loads the policy via
            :func:`ai_hedge_fund.review.policy.load_review_policy` and caches
            it. Exactly one of ``policy`` / ``policy_path`` MUST be provided.

    Raises:
        ValueError: When neither (or both) of ``policy`` / ``policy_path``
            is supplied. Enforced at construction via ``__post_init__``.
    """

    db_session: Session
    policy: ReviewPolicy | None = None
    policy_path: Path | None = None

    def __post_init__(self) -> None:
        # XOR: exactly one of policy / policy_path must be provided.
        if (self.policy is None) == (self.policy_path is None):
            raise ValueError(
                "ReviewDeps requires exactly one of policy or policy_path",
            )
