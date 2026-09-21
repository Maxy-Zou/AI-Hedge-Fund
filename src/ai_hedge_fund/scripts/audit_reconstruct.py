"""Reconstruct the audit trail for a final signal (Phase 8 SIG-04).

Given an ``episodic_id`` pointing at a ``record_type='analysis'`` row, this
tool returns the full compliance-grade trail:

    1. The analysis row itself (id, ticker, sector, as_of_date, policy_sha,
       full payload).
    2. The linked ``record_type='review'`` row (if any) -- latest by id.
    3. A Langfuse trace-lookup hint (``thread_id`` derivable from
       ``analysis.ticker`` + ``analysis.as_of_date``).

The function :func:`reconstruct_audit_trail` is pure (no I/O beyond the
supplied session). The :func:`_main` entry point is the CLI wrapper,
shaped like :mod:`scripts.ingest_outcome` but SYNCHRONOUS (no ``asyncio``
-- audit queries don't need it).

Usage::

    uv run python -m ai_hedge_fund.scripts.audit_reconstruct \\
        --episodic-id 7

Closes Phase-8 Pitfall G (audit-trail technically complete but impossible
to reconstruct).

Threat mitigation T-08-19 (repudiation / empty trail): explicit
:class:`ValueError` on non-analysis ids + ``policy_sha`` +
``review_policy_sha`` + ``thread_id`` hint in every successful result.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory

logger = structlog.get_logger(__name__)


def reconstruct_audit_trail(session: Session, episodic_id: int) -> dict[str, Any]:
    """Reconstruct the full audit trail for a final signal.

    Args:
        session: Open SQLAlchemy session.
        episodic_id: Primary key of a ``record_type='analysis'`` row.

    Returns:
        Dict with ``analysis_row``, ``review_row`` (or ``None``), and
        ``langfuse_trace_hint``.

    Raises:
        ValueError: if ``episodic_id`` does not correspond to a
            ``record_type='analysis'`` row (missing id OR wrong record type).
    """
    analysis = session.get(EpisodicMemory, episodic_id)
    if analysis is None or analysis.record_type != "analysis":
        found = analysis.record_type if analysis is not None else "None"
        raise ValueError(f"No analysis row at id {episodic_id} (found: {found})")

    review = session.scalars(
        select(EpisodicMemory)
        .where(EpisodicMemory.record_type == "review")
        .where(EpisodicMemory.linked_analysis_id == episodic_id)
        .order_by(EpisodicMemory.id.desc())
    ).first()

    as_of_str = (
        analysis.as_of_date.isoformat()[:10]
        if hasattr(analysis.as_of_date, "isoformat")
        else str(analysis.as_of_date)[:10]
    )

    result: dict[str, Any] = {
        "analysis_row": {
            "id": analysis.id,
            "ticker": analysis.ticker,
            "sector": analysis.sector,
            "as_of_date": as_of_str,
            "record_type": analysis.record_type,
            "signal_direction": analysis.signal_direction,
            "confidence": analysis.confidence,
            "policy_sha": analysis.policy_sha,
            "payload": analysis.payload,
        },
        "review_row": None,
        "langfuse_trace_hint": {
            "thread_id": f"analysis-{analysis.ticker}-{as_of_str}",
            "instruction": (
                "Search Langfuse by thread_id for the full per-agent span "
                "trail (inputs, outputs, reasoning, model, tokens, duration, "
                "timestamp)."
            ),
        },
    }

    if review is not None:
        review_payload = review.payload or {}
        result["review_row"] = {
            "id": review.id,
            "linked_analysis_id": review.linked_analysis_id,
            "status": review_payload.get("review_status"),
            "review_policy_sha": review_payload.get("review_policy_sha"),
            "policy_sha": review.policy_sha,
            "payload": review.payload,
        }

    logger.info(
        "audit_reconstruct_complete",
        episodic_id=episodic_id,
        ticker=analysis.ticker,
        has_review=result["review_row"] is not None,
    )
    return result


def _main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Parses ``--episodic-id`` (required) and optional ``--database-url``,
    opens a session, calls :func:`reconstruct_audit_trail`, and prints the
    result as pretty-printed JSON to stdout.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` via argparse).

    Returns:
        ``0`` on success, ``1`` if the id is not a valid analysis row.
    """
    from ai_hedge_fund.config import AppSettings
    from ai_hedge_fund.db import session as session_mod

    parser = argparse.ArgumentParser(
        description="Reconstruct the audit trail for a final signal (Phase 8 SIG-04).",
    )
    parser.add_argument("--episodic-id", type=int, required=True)
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Override DATABASE_URL from env",
    )
    args = parser.parse_args(argv)

    settings = AppSettings()
    url = args.database_url or settings.database_url
    engine = session_mod.get_engine(url)
    factory = session_mod.get_session_factory(engine)
    session = factory()
    try:
        try:
            result = reconstruct_audit_trail(session, args.episodic_id)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, default=str))
        return 0
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(_main())
