"""Recursive secret redaction for broker payloads (Phase 10, 09-PREMORTEM #7).

Broker request/response objects nest credentials (headers, config blocks), so
the top-level-only tripwire in ``paper.records`` is not enough before a broker
response becomes a stored ``payload``. ``redact`` walks dicts and lists to any
depth, masking values whose key looks secret, and optionally scrubbing known
secret *values* wherever they appear inside strings. It returns a copy; the
input is never mutated.
"""

from __future__ import annotations

import re
from typing import Any

SECRET_KEY = re.compile(r"(^|_)(secret|api_key|token|password|authorization)(_|$)", re.IGNORECASE)
_MASK = "***"


def redact(obj: Any, secret_values: list[str] | None = None) -> Any:
    """Return a deep copy of ``obj`` with secret-like keys masked.

    Args:
        obj: any JSON-like structure (dict / list / scalar).
        secret_values: literal strings (e.g. the API key and secret) to scrub
            from every string value, even under a benign key.
    """
    values = [v for v in (secret_values or []) if v]

    def _scrub_str(s: str) -> str:
        for v in values:
            s = s.replace(v, _MASK)
        return s

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                k: (_MASK if isinstance(k, str) and SECRET_KEY.search(k) else _walk(v))
                for k, v in node.items()
            }
        if isinstance(node, list):
            return [_walk(item) for item in node]
        if isinstance(node, str):
            return _scrub_str(node)
        return node

    return _walk(obj)
