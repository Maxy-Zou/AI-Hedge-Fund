"""Phase 10 T6 -- submit orchestration (EXEC-01..04; 09-PREMORTEM #2/#5/#8/#10/#11/#12/#22/#23)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.execution.decide import OrderPlan
from ai_hedge_fund.execution.errors import (
    AlreadyDecided,
    AlreadySubmitted,
    AttemptsExhausted,
    BrokerRejected,
)
from ai_hedge_fund.execution.policy import ExecutionPolicy
from ai_hedge_fund.execution.submit import NO_REVIEW_POLICY_SHA, SubmitDeps, submit_signal
from ai_hedge_fund.paper import PaperTradeRecord
from ai_hedge_fund.paper.recall import query_paper_trades
from tests.execution.conftest import add_price, add_review, make_analysis
from tests.execution.fakes import FakeBroker

POLICY = ExecutionPolicy(
    nav_cents=10_000_000,
    max_position_pct=0.05,
    min_conviction=55,
    full_conviction=90,
    long_only=True,
    max_attempts=3,
    order_type="market",
    limit_offset_bps=25,
)
POLICY_SHA = "e" * 64


def _deps(db_session: Session, broker: FakeBroker | None = None) -> SubmitDeps:
    return SubmitDeps(
        db_session=db_session, broker=broker or FakeBroker(), policy=POLICY, policy_sha=POLICY_SHA
    )


# --------------------------------------------------------------------------- happy path


def test_submitted_persists_broker_order_id(db_session: Session, reviewed_signal: int) -> None:
    broker = FakeBroker()
    rec = submit_signal(_deps(db_session, broker), reviewed_signal)
    assert isinstance(rec, PaperTradeRecord)
    assert rec.submit_status == "submitted" and rec.broker_order_id == "fake-1"
    # conviction 80 -> scale (80-55)/(90-55)=25/35; budget 500_000c * 25/35 = 357142c; //10_000 = 35
    assert rec.quantity == 35 and rec.attempt_no == 1
    assert broker.calls == 1
    assert rec.payload["execution_policy_sha"] == POLICY_SHA
    assert broker.requests[0].client_order_id == f"sig-{reviewed_signal}-a1"


def test_dry_run_writes_nothing_and_calls_no_broker(
    db_session: Session, reviewed_signal: int
) -> None:
    broker = FakeBroker()
    out = submit_signal(_deps(db_session, broker), reviewed_signal, dry_run=True)
    assert isinstance(out, OrderPlan)
    assert broker.calls == 0
    assert query_paper_trades(db_session, as_of_date="2999-01-01", signal_id=reviewed_signal) == []


# --------------------------------------------------------------------------- idempotency (EXEC-03)


def test_second_submit_raises_already_submitted_without_broker_call(
    db_session: Session, reviewed_signal: int
) -> None:
    broker = FakeBroker()
    submit_signal(_deps(db_session, broker), reviewed_signal)
    with pytest.raises(AlreadySubmitted):
        submit_signal(_deps(db_session, broker), reviewed_signal)
    assert broker.calls == 1  # no second order
    assert (
        len(query_paper_trades(db_session, as_of_date="2999-01-01", signal_id=reviewed_signal)) == 1
    )


# --- circuit breaker (EXEC-04)


def test_vetoed_refused_zero_broker_calls(db_session: Session) -> None:
    aid = make_analysis(db_session, risk_status="VETOED")
    # a VETOED signal has no review row and no final_signal
    broker = FakeBroker()
    rec = submit_signal(_deps(db_session, broker), aid)
    assert isinstance(rec, PaperTradeRecord)
    assert rec.submit_status == "refused_veto" and rec.broker_order_id is None
    assert rec.quantity == 0
    assert broker.calls == 0
    assert rec.review_policy_sha == NO_REVIEW_POLICY_SHA
    assert rec.payload["refusal_reason"] == "risk_vetoed"


def test_vetoed_is_terminal(db_session: Session) -> None:
    aid = make_analysis(db_session, risk_status="VETOED")
    submit_signal(_deps(db_session), aid)
    with pytest.raises(AlreadyDecided):
        submit_signal(_deps(db_session), aid)


# --------------------------------------------------------------------------- refusals recorded


def test_review_rejected_records_refused_review(db_session: Session) -> None:
    aid = make_analysis(db_session)
    add_review(db_session, aid, review_status="REJECTED")
    add_price(db_session)
    rec = submit_signal(_deps(db_session), aid)
    assert (
        rec.submit_status == "refused_review" and rec.payload["refusal_reason"] == "review_rejected"
    )


def test_no_price_records_refused_policy(db_session: Session) -> None:
    aid = make_analysis(db_session)
    add_review(db_session, aid)  # no price row seeded
    rec = submit_signal(_deps(db_session), aid)
    assert rec.submit_status == "refused_policy" and rec.payload["refusal_reason"] == "no_price"


def test_refusal_is_terminal(db_session: Session) -> None:
    aid = make_analysis(db_session)
    add_review(db_session, aid, review_status="REJECTED")
    add_price(db_session)
    submit_signal(_deps(db_session), aid)
    with pytest.raises(AlreadyDecided):
        submit_signal(_deps(db_session), aid)


# --- broker rejection (retry)


def test_broker_rejection_recorded_then_reraised(db_session: Session, reviewed_signal: int) -> None:
    broker = FakeBroker(fail_with=BrokerRejected("insufficient buying power"))
    with pytest.raises(BrokerRejected):
        submit_signal(_deps(db_session, broker), reviewed_signal)
    rows = query_paper_trades(db_session, as_of_date="2999-01-01", signal_id=reviewed_signal)
    assert len(rows) == 1 and rows[0].submit_status == "rejected"
    assert rows[0].broker_order_id is None


def test_retry_after_rejection_is_attempt_2(db_session: Session, reviewed_signal: int) -> None:
    bad = FakeBroker(fail_with=BrokerRejected("try later"))
    with pytest.raises(BrokerRejected):
        submit_signal(_deps(db_session, bad), reviewed_signal)
    good = FakeBroker()
    rec = submit_signal(_deps(db_session, good), reviewed_signal)
    assert rec.submit_status == "submitted" and rec.attempt_no == 2
    assert good.requests[0].client_order_id == f"sig-{reviewed_signal}-a2"


def test_attempts_exhausted(db_session: Session, reviewed_signal: int) -> None:
    for _ in range(POLICY.max_attempts):
        with pytest.raises(BrokerRejected):
            submit_signal(
                _deps(db_session, FakeBroker(fail_with=BrokerRejected("no"))), reviewed_signal
            )
    with pytest.raises(AttemptsExhausted):
        submit_signal(_deps(db_session, FakeBroker()), reviewed_signal)


# --------------------------------------------------------------------------- context loading


def test_latest_review_row_wins(db_session: Session) -> None:
    """09-PREMORTEM #22: a later APPROVED re-review must win over an earlier REJECTED."""
    aid = make_analysis(db_session)
    add_review(db_session, aid, review_status="REJECTED")
    add_review(db_session, aid, review_status="APPROVED")  # later id
    add_price(db_session)
    rec = submit_signal(_deps(db_session), aid)
    assert rec.submit_status == "submitted"


def test_unknown_episodic_id_raises(db_session: Session) -> None:
    with pytest.raises(ValueError, match="analysis"):
        submit_signal(_deps(db_session), 999_999)


def test_no_secret_values_in_payload(db_session: Session, reviewed_signal: int) -> None:
    rec = submit_signal(_deps(db_session), reviewed_signal)
    import json

    blob = json.dumps(rec.payload).lower()
    assert "secret" not in blob or "***" in blob  # no raw secret key names leak unmasked
