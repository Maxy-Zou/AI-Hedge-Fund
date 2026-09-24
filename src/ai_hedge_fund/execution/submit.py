"""Submit orchestration: an episodic analysis id -> a recorded paper trade (Phase 10, D1/D3/D4).

A standalone step (not a graph node): its input is an id, so it is idempotent by
construction and never rides the LLM run's checkpointer. It loads the stored
analysis + latest review, decides (pure), and appends exactly one append-only
row -- a submitted/rejected order or a typed refusal. Idempotency is enforced
twice: ``next_attempt`` refuses to resubmit a settled signal, and the broker
sees a unique ``client_order_id`` per attempt.

The client_order_id is stable across re-runs of one attempt, so a re-run after
a lost broker response gets "duplicate" -- and then adopts the order the broker
already holds (after checking it is the order we would place) instead of
leaving it unrecorded (review R3). The id is namespaced by the analysis row's
observed timestamp so a rebuilt database reissuing row id 1 cannot collide with
the old database's orders in the same long-lived paper account (review R7).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.execution.broker import BrokerClient, BrokerOrderRequest, BrokerOrderResult
from ai_hedge_fund.execution.decide import Decision, OrderPlan, Refusal, decide
from ai_hedge_fund.execution.errors import (
    AlreadyDecided,
    AlreadySubmitted,
    AttemptsExhausted,
    BrokerRejected,
    ClientOrderIdConflict,
    DuplicateClientOrderId,
    NoPriceAvailable,
    SignalNotReviewed,
)
from ai_hedge_fund.execution.policy import ExecutionPolicy
from ai_hedge_fund.execution.prices import latest_adj_close_cents
from ai_hedge_fund.paper import NewPaperTrade, PaperTradeRecord, insert_paper_trade
from ai_hedge_fund.paper.recall import query_paper_trades

logger = structlog.get_logger(__name__)

# Placeholder review_policy_sha for a refusal that occurs before the review stage
# (a VETOED signal never reaches review, so it has no real review policy fingerprint).
NO_REVIEW_POLICY_SHA = "0" * 64
_FAR_FUTURE = "2999-01-01"


@dataclass(frozen=True)
class SubmitDeps:
    db_session: Session
    broker: BrokerClient
    policy: ExecutionPolicy
    policy_sha: str


@dataclass(frozen=True)
class SignalContext:
    signal_id: int
    ticker: str
    as_of_date: str
    risk_status: str
    review_status: str | None
    final_signal: dict[str, Any] | None
    policy_sha: str
    review_policy_sha: str
    signal_observed_at: str  # analysis row's observed_date; namespaces client_order_id


def client_order_id_for(ctx: SignalContext, attempt: int) -> str:
    """``sig-<id>-a<attempt>-<tag>``: stable for one attempt, distinct across databases.

    ``tag`` hashes the analysis row's identity *including* its observed timestamp,
    which a rebuilt database cannot reproduce for a reissued row id.
    """
    identity = f"{ctx.signal_id}|{ctx.ticker}|{ctx.signal_observed_at}"
    tag = hashlib.sha256(identity.encode()).hexdigest()[:10]
    return f"sig-{ctx.signal_id}-a{attempt}-{tag}"


def load_signal_context(db_session: Session, episodic_id: int) -> SignalContext:
    """Load the analysis row and its latest review row into a decision context.

    Raises:
        ValueError: no ``record_type='analysis'`` row at ``episodic_id``.
        SignalNotReviewed: a non-vetoed analysis has no review row to act on.
    """
    analysis = db_session.get(EpisodicMemory, episodic_id)
    if analysis is None or analysis.record_type != "analysis":
        found = analysis.record_type if analysis is not None else "None"
        raise ValueError(f"no analysis row at episodic id {episodic_id} (found: {found})")

    payload = analysis.payload or {}
    risk_status = (payload.get("risk_assessment") or {}).get("status") or "UNKNOWN"
    as_of_str = _as_of_str(analysis.as_of_date)
    observed = analysis.observed_date.isoformat()
    risk_sha = analysis.policy_sha or NO_REVIEW_POLICY_SHA

    review = db_session.scalars(
        select(EpisodicMemory)
        .where(EpisodicMemory.record_type == "review")
        .where(EpisodicMemory.linked_analysis_id == episodic_id)
        .order_by(EpisodicMemory.id.desc())  # latest review wins (09-PREMORTEM #22)
    ).first()

    if review is None:
        # A VETOED signal never reaches review by construction -- decide on the veto alone.
        if risk_status == "VETOED":
            return SignalContext(
                signal_id=episodic_id,
                ticker=analysis.ticker,
                as_of_date=as_of_str,
                risk_status=risk_status,
                review_status=None,
                final_signal=None,
                policy_sha=risk_sha,
                review_policy_sha=NO_REVIEW_POLICY_SHA,
                signal_observed_at=observed,
            )
        raise SignalNotReviewed(f"analysis {episodic_id} has no review row")

    rpayload = review.payload or {}
    final_signal = rpayload.get("final_signal")
    review_sha = (
        rpayload.get("review_policy_sha")
        or (final_signal or {}).get("review_policy_sha")
        or NO_REVIEW_POLICY_SHA
    )
    return SignalContext(
        signal_id=episodic_id,
        ticker=analysis.ticker,
        as_of_date=as_of_str,
        risk_status=risk_status,
        review_status=rpayload.get("review_status"),
        final_signal=final_signal,
        policy_sha=risk_sha,
        review_policy_sha=review_sha,
        signal_observed_at=observed,
    )


def next_attempt(db_session: Session, signal_id: int, policy: ExecutionPolicy) -> int:
    """Attempt number for the next submission, enforcing idempotency (D3).

    Raises AlreadySubmitted / AlreadyDecided when the signal is settled, and
    AttemptsExhausted when retries after rejection reach ``max_attempts``.
    """
    rows = query_paper_trades(db_session, as_of_date=_FAR_FUTURE, signal_id=signal_id, limit=1000)
    if not rows:
        return 1
    latest = rows[0]  # newest first
    if latest.submit_status == "submitted":
        raise AlreadySubmitted(
            f"signal {signal_id} already submitted (order {latest.broker_order_id})"
        )
    if latest.submit_status.startswith("refused"):
        raise AlreadyDecided(f"signal {signal_id} already decided: {latest.submit_status}")
    # latest is 'rejected' -> a retry is allowed
    nxt = max(r.attempt_no for r in rows) + 1
    if nxt > policy.max_attempts:
        raise AttemptsExhausted(f"signal {signal_id} reached max_attempts={policy.max_attempts}")
    return nxt


def submit_signal(
    deps: SubmitDeps, episodic_id: int, *, dry_run: bool = False
) -> PaperTradeRecord | Decision:
    """Decide and record one paper trade for an analysis id. Returns the row, or the
    Decision when ``dry_run`` (writes nothing, calls no broker)."""
    ctx = load_signal_context(deps.db_session, episodic_id)
    attempt = next_attempt(deps.db_session, ctx.signal_id, deps.policy)

    try:
        price_cents: int | None = latest_adj_close_cents(
            deps.db_session, ctx.ticker, ctx.as_of_date
        )
    except NoPriceAvailable:
        price_cents = None

    decision = decide(
        ctx.final_signal,
        risk_status=ctx.risk_status,
        review_status=ctx.review_status,
        price_cents=price_cents,
        policy=deps.policy,
    )
    if dry_run:
        return decision

    if isinstance(decision, Refusal):
        return _record_refusal(deps, ctx, attempt, decision)
    return _submit_order(deps, ctx, attempt, decision, price_cents)


def _base_payload(deps: SubmitDeps, ctx: SignalContext) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "execution_policy_sha": deps.policy_sha,
        "final_signal": ctx.final_signal,
    }


def _record_refusal(
    deps: SubmitDeps, ctx: SignalContext, attempt: int, refusal: Refusal
) -> PaperTradeRecord:
    payload = _base_payload(deps, ctx)
    payload["refusal_reason"] = refusal.reason
    payload["decision"] = refusal.model_dump()
    # order_type='market' + no limit price keeps the refusal row past the paired CHECK.
    rec = insert_paper_trade(
        deps.db_session,
        NewPaperTrade(
            signal_id=ctx.signal_id,
            attempt_no=attempt,
            ticker=ctx.ticker,
            side=_side_hint(ctx),
            order_type="market",
            quantity=0,
            limit_price_cents=None,
            submit_status=refusal.status,
            broker_order_id=None,
            risk_status_at_submit=ctx.risk_status,
            policy_sha=ctx.policy_sha,
            review_policy_sha=ctx.review_policy_sha,
            as_of_date=ctx.as_of_date,
            payload=payload,
        ),
    )
    logger.info(
        "paper_trade_refused", signal_id=ctx.signal_id, status=refusal.status, reason=refusal.reason
    )
    return rec


def _submit_order(
    deps: SubmitDeps, ctx: SignalContext, attempt: int, plan: OrderPlan, price_cents: int | None
) -> PaperTradeRecord:
    client_order_id = client_order_id_for(ctx, attempt)
    req = BrokerOrderRequest(
        client_order_id=client_order_id,
        symbol=ctx.ticker,
        side=plan.side,
        qty=plan.quantity,
        order_type=plan.order_type,
        limit_price_cents=plan.limit_price_cents,
    )
    payload = _base_payload(deps, ctx)
    payload["decision"] = plan.model_dump()
    payload["client_order_id"] = client_order_id

    try:
        result = deps.broker.submit_order(req)
    except DuplicateClientOrderId:
        result = _adopt_existing_order(deps, req)
        payload["adopted_existing_order"] = True
    except BrokerRejected as exc:
        # The adapter scrubs credentials from broker messages before they get here.
        payload["broker_error"] = str(exc)
        insert_paper_trade(deps.db_session, _trade_row(ctx, attempt, plan, "rejected", payload))
        logger.warning("paper_order_rejected", signal_id=ctx.signal_id, attempt=attempt)
        raise

    payload["broker_result"] = result.raw
    rec = insert_paper_trade(
        deps.db_session,
        _trade_row(ctx, attempt, plan, "submitted", payload, result.broker_order_id),
    )
    logger.info(
        "paper_order_submitted",
        signal_id=ctx.signal_id,
        attempt=attempt,
        broker_order_id=result.broker_order_id,
        qty=plan.quantity,
        adopted=payload.get("adopted_existing_order", False),
    )
    return rec


def _adopt_existing_order(deps: SubmitDeps, req: BrokerOrderRequest) -> BrokerOrderResult:
    """The broker already holds ``req.client_order_id`` -- a previous run of this
    attempt reached the broker but its response was lost (next_attempt found no
    local row). Adopt that order, but only if it is the order we would place."""
    held = deps.broker.get_order_by_client_order_id(req.client_order_id)
    if held is None:
        raise ClientOrderIdConflict(
            f"broker reported {req.client_order_id} as a duplicate but cannot find it"
        )
    ours = (req.symbol.upper(), req.side, req.qty)
    theirs = (held.symbol.upper(), held.side, held.qty)
    if theirs != ours:
        raise ClientOrderIdConflict(
            f"broker holds {req.client_order_id} as {theirs}, not the intended {ours}"
        )
    logger.warning(
        "paper_order_adopted",
        client_order_id=req.client_order_id,
        broker_order_id=held.broker_order_id,
    )
    return held


def _trade_row(
    ctx: SignalContext,
    attempt: int,
    plan: OrderPlan,
    status: Literal["submitted", "rejected"],
    payload: dict[str, Any],
    broker_order_id: str | None = None,
) -> NewPaperTrade:
    return NewPaperTrade(
        signal_id=ctx.signal_id,
        attempt_no=attempt,
        ticker=ctx.ticker,
        side=plan.side,
        order_type=plan.order_type,
        quantity=plan.quantity,
        limit_price_cents=plan.limit_price_cents,
        submit_status=status,
        broker_order_id=broker_order_id,
        risk_status_at_submit=ctx.risk_status,
        policy_sha=ctx.policy_sha,
        review_policy_sha=ctx.review_policy_sha,
        as_of_date=ctx.as_of_date,
        payload=payload,
    )


def _side_hint(ctx: SignalContext) -> str:
    direction = (ctx.final_signal or {}).get("direction")
    return "sell" if direction == "short" else "buy"


def _as_of_str(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value)[:10]
