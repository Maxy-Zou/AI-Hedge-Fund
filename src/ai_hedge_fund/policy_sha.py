"""Canonical-JSON SHA-256 fingerprint for policy objects.

Single source of truth for the policy-versioning fingerprint used across the
audit chain. A policy's SHA is stamped onto every record it governs (risk
assessments, review decisions, paper trades) so any stored decision names the
exact policy bytes that produced it.

Promoted in Phase 10 from two byte-identical private copies
(``risk.policy.compute_policy_sha``, ``review.policy.compute_review_policy_sha``),
both of which now delegate here. The digest is unchanged, so existing
``policy_sha`` values in the database remain valid.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel


def fingerprint(model: BaseModel) -> str:
    """Return the lowercase 64-char SHA-256 hex of a model's canonical JSON.

    Canonical means ``model_dump(mode="json")`` serialized with ``sort_keys=True``
    and compact separators, so two semantically-identical policies share a
    fingerprint and any field change produces a different digest.
    """
    canonical = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
