"""Phase 10 T6 -- submit orchestration (EXEC-01..04; 09-PREMORTEM #2/#5/#8/#10/#11/#12/#22/#23)."""

from __future__ import annotations

import re
from dataclasses import replace

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.execution.decide import OrderPlan
from ai_hedge_fund.execution.errors import (
    AlreadyDecided,
    AlreadySubmitted,
    AttemptsExhausted,
    BrokerAuthError,
    BrokerRejected,
    ClientOrderIdConflict,
    InvalidSignal,
    TransientBrokerError,
)
from ai_hedge_fund.execution.policy import ExecutionPolicy
from ai_hedge_fund.execution.submit import (
    NO_REVIEW_POLICY_SHA,
    SubmitDeps,
    client_order_id_for,
    load_signal_context,
    submit_signal,
)
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
    assert broker.requests[0].client_order_id.startswith(f"sig-{reviewed_signal}-a1-")


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
    assert good.requests[0].client_order_id.startswith(f"sig-{reviewed_signal}-a2-")


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


# --------------------------------------------------------------------------- client_order_id (R7)


def test_client_order_id_is_namespaced_and_stable(
    db_session: Session, reviewed_signal: int
) -> None:
    """Review R7: the id must not be derivable from the row id alone, but must be
    identical on every re-run of the same attempt (idempotency depends on it)."""
    ctx = load_signal_context(db_session, reviewed_signal)
    coid = client_order_id_for(ctx, 1)
    assert re.fullmatch(rf"sig-{reviewed_signal}-a1-[0-9a-f]{{10}}", coid)
    assert client_order_id_for(ctx, 1) == coid
    assert client_order_id_for(ctx, 2) != coid
    assert len(coid) <= 128  # Alpaca's limit (probed)


def test_client_order_id_differs_for_same_row_id_in_another_database(
    db_session: Session, reviewed_signal: int
) -> None:
    """Review R7: a rebuilt DB reissues signal id 1 -- its orders must not collide
    with the old DB's orders in the same (long-lived) paper account."""
    ctx = load_signal_context(db_session, reviewed_signal)
    other_db = replace(ctx, signal_observed_at="2031-01-01T00:00:00")
    assert client_order_id_for(other_db, 1) != client_order_id_for(ctx, 1)


# --------------------------------------------------------------------------- lost responses (R3)


def test_lost_response_is_adopted_on_rerun(db_session: Session, reviewed_signal: int) -> None:
    """Review R3: the broker accepted, the response timed out. The re-run resends
    the same client_order_id, gets 'duplicate', and records the existing order
    instead of reporting 'already handled' with nothing recorded."""
    broker = FakeBroker(lose_response_once=True)
    with pytest.raises(TransientBrokerError):
        submit_signal(_deps(db_session, broker), reviewed_signal)
    assert query_paper_trades(db_session, as_of_date="2999-01-01", signal_id=reviewed_signal) == []

    rec = submit_signal(_deps(db_session, broker), reviewed_signal)
    assert rec.submit_status == "submitted" and rec.attempt_no == 1
    assert rec.broker_order_id == "fake-1"
    assert rec.payload["adopted_existing_order"] is True
    assert len(broker.orders) == 1  # one order at the broker, never two
    assert broker.requests[0].client_order_id == broker.requests[1].client_order_id


def test_duplicate_held_by_a_different_order_is_a_conflict(
    db_session: Session, reviewed_signal: int
) -> None:
    """Review R3/R7: never adopt a broker order that is not the one we would place."""
    broker = FakeBroker()
    coid = client_order_id_for(load_signal_context(db_session, reviewed_signal), 1)
    broker.seed_order(coid, symbol="MSFT", side="buy", qty=35)
    with pytest.raises(ClientOrderIdConflict):
        submit_signal(_deps(db_session, broker), reviewed_signal)
    assert query_paper_trades(db_session, as_of_date="2999-01-01", signal_id=reviewed_signal) == []


# --------------------------------------------------------------------------- auth failures (R5)


def test_auth_failure_records_nothing_and_burns_no_attempt(
    db_session: Session, reviewed_signal: int
) -> None:
    """Review R5: a 401 is not the broker's verdict on the order."""
    with pytest.raises(BrokerAuthError):
        submit_signal(
            _deps(db_session, FakeBroker(fail_with=BrokerAuthError("unauthorized."))),
            reviewed_signal,
        )
    assert query_paper_trades(db_session, as_of_date="2999-01-01", signal_id=reviewed_signal) == []
    rec = submit_signal(_deps(db_session, FakeBroker()), reviewed_signal)
    assert rec.submit_status == "submitted" and rec.attempt_no == 1


# ------------------------------------------------------------ stored-signal validation (R6)


@pytest.mark.parametrize(
    "overrides",
    [
        {"direction": "LONG"},
        {"conviction": 150},
        {"episodic_id": 424242},  # review row describes a different analysis
        {"ticker": "MSFT"},  # ...or a different ticker than the analysis row
        {"thesis_summary": None},
    ],
    ids=["direction", "conviction", "episodic_id", "ticker", "null-field"],
)
def test_malformed_stored_signal_raises_and_records_nothing(
    db_session: Session, overrides: dict
) -> None:
    """Review R6 / spec 3.8: the stored final_signal is validated against
    FinalSignalOutput before anything is decided. A malformed signal is a data
    error -- raised, not recorded (a refusal row would be terminal forever)."""
    aid = make_analysis(db_session)
    add_review(db_session, aid, signal_overrides=overrides)
    add_price(db_session)
    broker = FakeBroker()
    with pytest.raises(InvalidSignal):
        submit_signal(_deps(db_session, broker), aid)
    assert broker.calls == 0
    assert query_paper_trades(db_session, as_of_date="2999-01-01", signal_id=aid) == []


@pytest.mark.parametrize("risk_status", ["UNKNOWN", "approved"])
def test_unrecognised_risk_status_raises(db_session: Session, risk_status: str) -> None:
    aid = make_analysis(db_session, risk_status=risk_status)
    add_review(db_session, aid)
    add_price(db_session)
    with pytest.raises(InvalidSignal):
        submit_signal(_deps(db_session), aid)


def test_unrecognised_review_status_raises(db_session: Session) -> None:
    aid = make_analysis(db_session)
    add_review(db_session, aid, review_status="MAYBE")
    add_price(db_session)
    with pytest.raises(InvalidSignal):
        submit_signal(_deps(db_session), aid)


def test_loads_real_review_store_shape(db_session: Session) -> None:
    """09-PREMORTEM #23: the fixture's final_signal is FinalSignalOutput's own dump
    (review_store_node stores model_dump(mode='json')), so it must validate."""
    from ai_hedge_fund.schemas.signal_output import FinalSignalOutput

    aid = make_analysis(db_session)
    add_review(db_session, aid, review_status="APPROVED")
    ctx = load_signal_context(db_session, aid)
    assert FinalSignalOutput.model_validate(ctx.final_signal).episodic_id == aid
