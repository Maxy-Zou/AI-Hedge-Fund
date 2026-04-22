"""Ingest a trade outcome and run self-critique (MEM-04).

Operator workflow (offline, serial-per-ticker):
    1. Validate ticker via :func:`belief_path_for_ticker` (T-07-40 guard).
    2. Append an outcome row to ``episodic_memory`` (append-only).
    3. Compute the new confidence via :func:`compute_new_confidence`
       (deterministic Python; Pattern 2).
    4. Ask :attr:`self_critique_agent` to produce a rationale
       (:class:`RationaleOnly`; LLM cannot author the number).
    5. Apply the patch via :func:`write_belief` (MEM-03 human-edit guard
       enforced at the writer; audit dict returned for operator review).

Called from the CLI as::

    uv run python -m ai_hedge_fund.scripts.ingest_outcome \\
        --ticker AAPL --outcome-pct 4.2 --as-of 2026-04-20 \\
        --beliefs-dir ./beliefs

Threat mitigations:
    T-07-40 (Path traversal): ticker passes through
            :func:`belief_path_for_ticker` which enforces the
            ``[A-Z0-9.\\-]{1,10}`` regex before joining to disk.
    T-07-41 (Outcome poisoning): CLI-operator-only path with no network
            surface. Operator-allowlist / signed broker outcomes is a v2
            hardening item; for v1 this is an operator-trust assumption.
    T-07-35 (Silent human-edit overwrite): :func:`write_belief` is the
            sole mutation entry; its return dict surfaces every skipped
            field with a structured reason code that is logged via
            structlog for operator audit.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_hedge_fund.agents.self_critique import (
    get_self_critique_limits,
    self_critique_agent,
)
from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.memory.beliefs import (
    belief_path_for_ticker,
    load_belief,
    write_belief,
)
from ai_hedge_fund.memory.critique import (
    compute_new_confidence,
    format_critique_context,
)

logger = structlog.get_logger(__name__)


def _latest_analysis(session: Session, ticker: str) -> EpisodicMemory | None:
    """Return the most recent ``record_type='analysis'`` row for ``ticker``."""
    return session.scalars(
        select(EpisodicMemory)
        .where(EpisodicMemory.ticker == ticker)
        .where(EpisodicMemory.record_type == "analysis")
        .order_by(EpisodicMemory.as_of_date.desc())
        .limit(1)
    ).one_or_none()


def _append_outcome_row(
    session: Session,
    ticker: str,
    outcome_pct: float,
    as_of_date: date,
    analysis: EpisodicMemory | None,
) -> EpisodicMemory:
    """Insert a single ``record_type='outcome'`` row and return it.

    Append-only: commits immediately so the DB write survives a
    subsequent exception in the rationale step.
    """
    sector = analysis.sector if analysis else "Unknown"
    outcome_row = EpisodicMemory(
        ticker=ticker,
        sector=sector,
        record_type="outcome",
        signal_direction=analysis.signal_direction if analysis else None,
        outcome_pct=outcome_pct,
        linked_analysis_id=analysis.id if analysis else None,
        policy_sha=analysis.policy_sha if analysis else None,
        as_of_date=datetime(as_of_date.year, as_of_date.month, as_of_date.day, tzinfo=UTC),
        payload={
            "schema_version": 1,
            "source": "ingest_outcome",
            "linked_analysis_id": analysis.id if analysis else None,
        },
    )
    session.add(outcome_row)
    session.commit()
    session.refresh(outcome_row)
    return outcome_row


async def ingest_outcome(
    session: Session,
    beliefs_dir: Path,
    ticker: str,
    outcome_pct: float,
    as_of_date: date,
) -> dict[str, Any]:
    """Record an outcome and run the self-critique loop end-to-end.

    Args:
        session: Open SQLAlchemy session for ``episodic_memory`` writes.
        beliefs_dir: Root directory (contains ``tickers/`` subtree).
        ticker: Ticker symbol to critique (regex-guarded).
        outcome_pct: Realised outcome as percent (e.g., 4.2 = +4.2%).
        as_of_date: Business date of the outcome.

    Returns:
        Audit dict ``{"applied", "skipped", "outcome_row_id",
        "new_confidence"}``. ``applied``/``skipped`` come from
        :func:`write_belief`.

    Raises:
        ValueError: ticker fails the ``[A-Z0-9.\\-]{1,10}`` regex
            (T-07-40). Raised BEFORE any DB write or file access.
        FileNotFoundError: belief YAML does not exist. The outcome row
            IS still appended to ``episodic_memory`` before this raises
            -- callers can inspect the partial progress.
    """
    # 1. Validate ticker BEFORE touching disk or DB (T-07-40).
    belief_path = belief_path_for_ticker(beliefs_dir, ticker)

    # 2. Append the outcome row (append-only) -- commits immediately so
    #    the DB write survives any subsequent failure.
    analysis = _latest_analysis(session, ticker)
    outcome_row = _append_outcome_row(
        session=session,
        ticker=ticker,
        outcome_pct=outcome_pct,
        as_of_date=as_of_date,
        analysis=analysis,
    )

    # 3. Load the belief. FileNotFoundError here propagates AFTER the
    #    outcome row has been committed -- that is the documented
    #    "bootstrap case" behaviour (see test_ingest_outcome_missing_belief_file).
    #
    #    Emit a structured ``self_critique_missing_belief`` warning BEFORE
    #    re-raising so the orphan outcome row is recoverable via log grep
    #    (WR-02). Without this log, a reader of the episodic table cannot
    #    distinguish "operator ingested an outcome for a ticker with no
    #    belief yet" from "operator ingested and the belief update silently
    #    failed".
    if not belief_path.is_file():
        logger.warning(
            "self_critique_missing_belief",
            ticker=ticker,
            as_of_date=as_of_date.isoformat(),
            outcome_row_id=outcome_row.id,
            belief_path=str(belief_path),
        )
        raise FileNotFoundError(
            f"Belief file not found for {ticker}; run the analysis "
            f"pipeline first to auto-create {belief_path}"
        )
    belief, raw = load_belief(belief_path)

    # 4. Deterministic math (Pattern 2). When no linked analysis exists,
    #    we treat the outcome as ungraded -- 'neutral' penalises any
    #    significant move, which is the conservative default.
    signal_direction: str = (
        analysis.signal_direction
        if analysis is not None and analysis.signal_direction
        else "neutral"
    )
    new_confidence = compute_new_confidence(
        old_confidence=belief.confidence,
        outcome_pct=outcome_pct,
        signal_direction=signal_direction,
    )

    # 5. LLM rationale (advisory only). The prompt is deterministic so
    #    audit replay is reproducible.
    linked_payload: dict[str, Any] = (
        dict(analysis.payload) if (analysis and analysis.payload) else {}
    )
    prompt = format_critique_context(
        belief=belief,
        outcome_pct=outcome_pct,
        new_confidence=new_confidence,
        linked_analysis_payload=linked_payload,
    )
    result = await self_critique_agent.run(prompt, usage_limits=get_self_critique_limits())
    rationale = result.output.rationale

    # 6. Build the critique_history entry and apply via write_belief.
    #    write_belief is the SOLE mutation entry point (MEM-03 chokepoint);
    #    its return dict surfaces any human-edit skip for operator audit.
    new_event = {
        "as_of_date": as_of_date.isoformat(),
        "outcome_pct": outcome_pct,
        "old_confidence": belief.confidence,
        "new_confidence": new_confidence,
        "rationale": rationale,
        "source": "self_critique",
    }
    existing_history = list(raw.get("critique_history") or [])
    patches = {
        "confidence": new_confidence,
        "critique_history": existing_history + [new_event],
    }
    outcome = write_belief(belief_path, raw, patches=patches)

    logger.info(
        "self_critique_applied",
        ticker=ticker,
        as_of_date=as_of_date.isoformat(),
        outcome_pct=outcome_pct,
        old_confidence=belief.confidence,
        new_confidence=new_confidence,
        applied=outcome["applied"],
        skipped=outcome["skipped"],
        outcome_row_id=outcome_row.id,
    )
    return {
        "applied": outcome["applied"],
        "skipped": outcome["skipped"],
        "outcome_row_id": outcome_row.id,
        "new_confidence": new_confidence,
    }


def _main() -> int:  # pragma: no cover - CLI entry
    from ai_hedge_fund.config import AppSettings
    from ai_hedge_fund.db.session import get_engine, get_session_factory

    parser = argparse.ArgumentParser(description="Ingest a trade outcome and run self-critique.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--outcome-pct", type=float, required=True)
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--beliefs-dir", type=Path, required=True)
    parser.add_argument("--database-url", type=str, default=None)
    args = parser.parse_args()

    settings = AppSettings()
    url = args.database_url or settings.database_url
    engine = get_engine(url)
    factory = get_session_factory(engine)
    session = factory()
    try:
        result = asyncio.run(
            ingest_outcome(
                session=session,
                beliefs_dir=args.beliefs_dir,
                ticker=args.ticker,
                outcome_pct=args.outcome_pct,
                as_of_date=date.fromisoformat(args.as_of),
            )
        )
        print(
            f"applied={result['applied']} skipped={result['skipped']} "
            f"new_confidence={result['new_confidence']}"
        )
        return 0
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(_main())
