"""Run the full Phase 5+6+7+8 pipeline for a single (ticker, as_of_date).

The founder-facing CLI. Composes memory + risk + output + review into one
end-to-end run. Pauses via :func:`langgraph.types.interrupt` when conviction
>= :attr:`ReviewPolicy.conviction_threshold` and prompts the reviewer via
stdin; on resume, validates the decision payload via
:class:`ReviewDecision.model_validate` (T-08-04).

Usage::

    uv run python -m ai_hedge_fund.scripts.run_analysis \\
        --ticker AAPL --as-of 2026-04-20 --sector Technology

    # JSON output for downstream tools:
    uv run python -m ai_hedge_fund.scripts.run_analysis \\
        --ticker AAPL --as-of 2026-04-20 --json

Phase-8 SIG-01 + SIG-02 + SIG-03 + SIG-04 are delivered here as the first
user-facing surface.

Threat mitigations (see 08-04-PLAN.md::threat_model):
    T-08-08 (Tampering / thread_id collision): ``thread_id`` is suffixed with
            ``uuid.uuid4().hex[:8]`` so repeated runs for the same
            ``(ticker, as_of_date)`` never collide in the checkpointer
            (Pitfall J).
    T-08-30 (Spoofing / malformed reviewer payload): the default
            ``reviewer_io`` builds the ReviewDecision dict from constrained
            stdin prompts; the pipeline's ``human_review_node`` re-validates
            via :class:`ReviewDecision.model_validate`.
    T-08-33 (Repudiation / missing audit evidence): ``run_analysis_start``
            and ``run_analysis_complete`` structlog events emit every
            audit-relevant field (ticker, thread_id, conviction,
            review_status, episodic_stored_id, review_stored_id).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from ai_hedge_fund.graph.memory_deps import MemoryDeps
from ai_hedge_fund.graph.pipeline import build_debate_pipeline
from ai_hedge_fund.graph.review_deps import ReviewDeps
from ai_hedge_fund.graph.risk_deps import RiskDeps
from ai_hedge_fund.output import format_review_request_md, format_signal_md
from ai_hedge_fund.review.policy import (
    DEFAULT_REVIEW_POLICY_PATH,
    ReviewPolicy,
    compute_review_policy_sha,
    load_review_policy,
)
from ai_hedge_fund.risk.policy import DEFAULT_POLICY_PATH as DEFAULT_RISK_POLICY_PATH
from ai_hedge_fund.risk.policy import load_policy as load_risk_policy

logger = structlog.get_logger(__name__)


ReviewerIOCallable = Callable[[dict[str, Any], ReviewPolicy, str | None], dict[str, Any]]
PipelineFactoryCallable = Callable[..., Any]


def _default_reviewer_io(
    review_request: dict[str, Any],
    review_policy: ReviewPolicy,
    reviewer_id_override: str | None,
) -> dict[str, Any]:
    """Print the reviewer packet and read an APPROVED/REJECTED decision from stdin.

    Blocking by design. The v1 scope is a single attended reviewer on a local
    terminal (see 08-04-PLAN.md::threat_model T-08-32 -- DoS via detached
    terminal is accepted). Tests replace this with a stub returning a
    pre-canned decision so they never block.
    """
    print(format_review_request_md(review_request))
    print("")
    sys.stdout.flush()

    # Resolve reviewer_id: CLI arg > policy default > $USER > OS username.
    reviewer_id = (
        reviewer_id_override
        or review_policy.reviewer_id_default
        or os.environ.get("USER")
        or getpass.getuser()
    )

    answer = input("Approve (y) or reject (n)? ").strip().lower()
    if answer.startswith("y"):
        status = "APPROVED"
    elif answer.startswith("n"):
        status = "REJECTED"
    else:
        raise ValueError(f"Reviewer input must start with y or n (got: {answer!r})")

    # Enforce the documented 1-2000 char cap at prompt time so the reviewer
    # can correct an over-long paste BEFORE the pipeline fires its Pydantic
    # re-validation (which would bubble a ValidationError and drop the
    # in-progress input). Empty input is substituted with a deterministic
    # placeholder so the min-length invariant is never violated.
    while True:
        note = input("Reviewer note (1-2000 chars): ").strip()
        if not note:
            note = f"{status.lower()} without note"
        if len(note) <= 2000:
            break
        print(f"Note too long ({len(note)} chars; limit 2000). Try again.")

    sha = compute_review_policy_sha(review_policy)
    return {
        "status": status,
        "reviewer_id": reviewer_id,
        "reviewer_note": note,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_policy_sha": sha,
    }


async def run_analysis(
    *,
    session: Any,  # SQLAlchemy Session; typed loosely to avoid TYPE_CHECKING cycles
    ticker: str,
    as_of_date: str,
    sector: str,
    review_policy: ReviewPolicy,
    risk_policy: Any,  # RiskPolicy -- typed loosely for the same reason
    beliefs_dir: Path,
    thread_id: str | None = None,
    pipeline_factory: PipelineFactoryCallable = build_debate_pipeline,
    reviewer_io: ReviewerIOCallable = _default_reviewer_io,
    reviewer_id_override: str | None = None,
    checkpointer: Any = None,
) -> dict[str, Any]:
    """Run the composed pipeline for one ticker; handle interrupt/resume.

    The pipeline is built with all four Phase 6/7/8 kwargs
    (``with_memory``, ``with_risk``, ``with_output``, ``with_review``) plus an
    in-memory checkpointer so :func:`langgraph.types.interrupt` can persist
    state between the initial invocation and the ``Command(resume=...)``.

    Args:
        session: Open SQLAlchemy session used by memory / risk / review deps.
        ticker: Stock ticker to analyze.
        as_of_date: ISO ``YYYY-MM-DD`` temporal cutoff for data.
        sector: Sector name seeded into ``candidate_metadata``.
        review_policy: Pre-loaded :class:`ReviewPolicy`.
        risk_policy: Pre-loaded :class:`RiskPolicy`.
        beliefs_dir: Path to the belief-memory root (Phase-7 MEM-02).
        thread_id: Optional override; defaults to ``f"{ticker}-{as_of_date}-
            {uuid4().hex[:8]}"`` to guarantee uniqueness across runs
            (Pitfall J / T-08-08).
        pipeline_factory: Override for tests; defaults to
            :func:`build_debate_pipeline`.
        reviewer_io: Override for tests; takes
            ``(review_request, policy, reviewer_id_override)`` and returns a
            :class:`ReviewDecision`-compatible dict. Defaults to the blocking
            stdin prompt.
        reviewer_id_override: Value for ``--reviewer-id`` CLI override.
        checkpointer: Override; defaults to a fresh :class:`InMemorySaver`
            (interrupt+resume within one process only). Production
            deployments should pass an :class:`AsyncPostgresSaver` so a reviewer
            can resume across process restarts.

    Returns:
        Final pipeline state dict. Keys of interest: ``final_signal``,
        ``review_decision``, ``episodic_stored_id``, ``review_stored_id``.
    """
    # Build the daily-log-returns DataFrame that drawdown + correlation
    # checks require. We read daily_prices for (candidate ticker + existing
    # portfolio tickers), filter by trade_date <= as_of_date to preserve
    # temporal controls, pivot wide, and compute log returns.
    import numpy as np
    import pandas as pd
    from sqlalchemy import select

    from ai_hedge_fund.db.models import DailyPrice, PortfolioPosition

    if thread_id is None:
        thread_id = f"{ticker}-{as_of_date}-{uuid.uuid4().hex[:8]}"
    if checkpointer is None:
        checkpointer = InMemorySaver()

    as_of = datetime.fromisoformat(as_of_date).date()
    portfolio_tickers = [
        row[0] for row in session.execute(select(PortfolioPosition.ticker).distinct()).all()
    ]
    universe = sorted({ticker, *portfolio_tickers})
    price_rows = session.execute(
        select(DailyPrice.ticker, DailyPrice.trade_date, DailyPrice.adj_close_cents)
        .where(DailyPrice.ticker.in_(universe))
        .where(DailyPrice.trade_date <= as_of)
    ).all()
    if price_rows:
        prices = (
            pd.DataFrame(price_rows, columns=["ticker", "trade_date", "adj_close_cents"])
            .pivot(index="trade_date", columns="ticker", values="adj_close_cents")
            .sort_index()
        )
        returns_df = np.log(prices / prices.shift(1)).dropna(how="all")
    else:
        returns_df = pd.DataFrame()

    memory_deps = MemoryDeps(db_session=session, beliefs_path=beliefs_dir)
    risk_deps = RiskDeps(
        db_session=session,
        returns=returns_df,
        policy=risk_policy,
    )
    review_deps = ReviewDeps(db_session=session, policy=review_policy)

    graph = pipeline_factory(
        checkpointer=checkpointer,
        with_memory=True,
        memory_deps=memory_deps,
        with_risk=True,
        risk_deps=risk_deps,
        with_output=True,
        with_review=True,
        review_deps=review_deps,
    )

    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "ticker": ticker,
        "as_of_date": as_of_date,
        "candidate_metadata": {"sector": sector, "instrument_type": "equity"},
        "_review_threshold": review_policy.conviction_threshold,
    }

    logger.info(
        "run_analysis_start",
        ticker=ticker,
        as_of_date=as_of_date,
        sector=sector,
        thread_id=thread_id,
        review_threshold=review_policy.conviction_threshold,
    )

    # First invocation -- may fire an __interrupt__ value.
    first = await graph.ainvoke(initial_state, config=config)

    interrupts = first.get("__interrupt__") or []
    if interrupts:
        review_request = interrupts[0].value
        decision = reviewer_io(review_request, review_policy, reviewer_id_override)
        final = await graph.ainvoke(Command(resume=decision), config=config)
    else:
        final = first

    final_signal = final.get("final_signal") or {}
    review_decision = final.get("review_decision") or {}
    logger.info(
        "run_analysis_complete",
        ticker=ticker,
        as_of_date=as_of_date,
        thread_id=thread_id,
        direction=final_signal.get("direction"),
        conviction=final_signal.get("conviction"),
        review_status=(
            final_signal.get("review_status") or review_decision.get("status") or "NOT_REQUIRED"
        ),
        episodic_stored_id=final.get("episodic_stored_id"),
        review_stored_id=final.get("review_stored_id"),
    )
    return final


def _format_output(final_state: dict[str, Any], *, as_json: bool) -> str:
    """Format the final state for stdout.

    Three branches:
        1. VETOED (no final_signal, risk_assessment.status='VETOED') -> a
           ``BLOCKED BY RISK`` markdown block (or its JSON equivalent).
        2. No final_signal for any other reason -> ``NO SIGNAL`` with the
           error string, if present.
        3. Normal -> :func:`format_signal_md` or ``json.dumps(final_signal)``.
    """
    final_signal = final_state.get("final_signal")
    risk = final_state.get("risk_assessment") or {}

    # VETOED path -- surface the risk veto cleanly.
    if final_signal is None and risk.get("status") == "VETOED":
        payload = {
            "status": "BLOCKED_BY_RISK",
            "risk_assessment": risk,
            "episodic_stored_id": final_state.get("episodic_stored_id"),
        }
        if as_json:
            # Full SHAs intentional here: the JSON surface is the audit-grade
            # form piped into compliance pipelines, where the complete
            # 64-char policy_sha is required for tamper-evident linkage to
            # the DB-stored policy row. Human-readable truncation (T-08-14)
            # applies only to the markdown branch below.
            return json.dumps(payload, indent=2, default=str)
        sha = (risk.get("policy_sha") or "")[:12]
        return (
            f"# BLOCKED BY RISK\n\n"
            f"- ticker: {final_state.get('ticker', '-')}\n"
            f"- as_of_date: {final_state.get('as_of_date', '-')}\n"
            f"- rationale: {risk.get('rationale', '-')}\n"
            f"- risk_policy_sha: {sha}...\n"
        )

    # Pipeline error OR missing signal from upstream failure.
    if final_signal is None:
        if as_json:
            return json.dumps(
                {"status": "NO_SIGNAL", "error": final_state.get("error")},
                default=str,
            )
        return f"# NO SIGNAL\n\nerror: {final_state.get('error', '-')}\n"

    if as_json:
        # Full SHAs intentional: JSON output is the audit-grade surface.
        # See T-08-14 rationale in the VETOED branch above.
        return json.dumps(final_signal, indent=2, default=str)
    return format_signal_md(final_signal)


def _main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Parses arguments, loads policies, opens a session, and drives
    :func:`run_analysis`. Returns ``0`` on success or ``1`` on any unhandled
    exception bubbling out of the pipeline.
    """
    from ai_hedge_fund.config import AppSettings
    from ai_hedge_fund.db import session as session_mod

    parser = argparse.ArgumentParser(
        description="Run the full Phase 5+6+7+8 pipeline on one ticker.",
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--sector", default="Unknown")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--review-policy",
        type=Path,
        default=DEFAULT_REVIEW_POLICY_PATH,
    )
    parser.add_argument(
        "--risk-policy",
        type=Path,
        default=DEFAULT_RISK_POLICY_PATH,
    )
    parser.add_argument("--beliefs-dir", type=Path, default=Path("./beliefs"))
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Override DATABASE_URL from env",
    )
    parser.add_argument("--reviewer-id", default=None)
    args = parser.parse_args(argv)

    review_policy = load_review_policy(args.review_policy)
    risk_policy = load_risk_policy(args.risk_policy)

    settings = AppSettings()
    url = args.database_url or settings.database_url
    engine = session_mod.get_engine(url)
    factory = session_mod.get_session_factory(engine)
    session = factory()
    try:
        try:
            final = asyncio.run(
                run_analysis(
                    session=session,
                    ticker=args.ticker,
                    as_of_date=args.as_of,
                    sector=args.sector,
                    review_policy=review_policy,
                    risk_policy=risk_policy,
                    beliefs_dir=args.beliefs_dir,
                    reviewer_id_override=args.reviewer_id,
                )
            )
        except Exception as exc:  # noqa: BLE001 -- CLI boundary; surface broadly
            print(f"ERROR: {exc}", file=sys.stderr)
            logger.error("run_analysis_failed", error=str(exc), ticker=args.ticker)
            return 1
        print(_format_output(final, as_json=args.as_json))
        return 0
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(_main())
