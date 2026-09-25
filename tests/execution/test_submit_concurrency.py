"""Concurrent submit runs for one signal (Phase 10 review F6).

Two runs that both pass ``next_attempt`` before either records compute the same
attempt number. The broker dedupes them by client_order_id; the losing run then
hits the ``(signal_id, attempt_no)`` unique constraint. It must surface as the
same typed, benign error a sequential re-run gets (AlreadySubmitted /
AlreadyDecided), never a store-level DuplicateSubmission.

The SQLite tests interleave deterministically: the "other" run executes inside
the first run's price lookup, i.e. after its ``next_attempt`` and before any
insert. The PostgreSQL test runs two real threads on two connections.
No test here reaches a real broker -- FakeBroker only.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ai_hedge_fund.db.base import Base
from ai_hedge_fund.execution import submit as submit_mod
from ai_hedge_fund.execution.broker import BrokerOrderRequest, BrokerOrderResult
from ai_hedge_fund.execution.errors import AlreadyDecided, AlreadySubmitted, BrokerRejected
from ai_hedge_fund.execution.policy import ExecutionPolicy
from ai_hedge_fund.execution.submit import SubmitDeps, submit_signal
from ai_hedge_fund.paper import PaperTradeRecord
from ai_hedge_fund.paper.recall import query_paper_trades
from tests.execution.conftest import add_price, add_review, make_analysis
from tests.execution.fakes import FakeBroker
from tests.paper.test_migration_roundtrip import _pg_url_or_skip

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


class LockedBroker(FakeBroker):
    """FakeBroker whose check-and-place is atomic across threads (Alpaca's is)."""

    def __init__(self, fail_with: Exception | None = None) -> None:
        super().__init__(fail_with)
        self._lock = threading.Lock()

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        with self._lock:
            return super().submit_order(req)


def _deps(session: Session, broker: FakeBroker) -> SubmitDeps:
    return SubmitDeps(db_session=session, broker=broker, policy=POLICY, policy_sha=POLICY_SHA)


def _rows(session: Session, signal_id: int) -> list[PaperTradeRecord]:
    return query_paper_trades(session, as_of_date="2999-01-01", signal_id=signal_id)


def _race_inside_price_lookup(
    monkeypatch: pytest.MonkeyPatch, other_run: Callable[[], object]
) -> list[object]:
    """Run ``other_run`` to completion the first time submit looks up a price."""
    real = submit_mod.latest_adj_close_cents
    outcome: list[object] = []

    def hooked(*args: object, **kwargs: object) -> int:
        if not outcome:
            outcome.append("started")
            outcome.append(other_run())
        return real(*args, **kwargs)

    monkeypatch.setattr(submit_mod, "latest_adj_close_cents", hooked)
    return outcome


# --------------------------------------------------------------------------- SQLite, interleaved


def test_losing_order_run_raises_already_submitted(
    db_session: Session, reviewed_signal: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    broker = FakeBroker()
    other = _race_inside_price_lookup(
        monkeypatch, lambda: submit_signal(_deps(db_session, broker), reviewed_signal)
    )
    with pytest.raises(AlreadySubmitted):
        submit_signal(_deps(db_session, broker), reviewed_signal)

    winner = other[1]
    assert isinstance(winner, PaperTradeRecord) and winner.submit_status == "submitted"
    rows = _rows(db_session, reviewed_signal)
    assert [(r.attempt_no, r.submit_status) for r in rows] == [(1, "submitted")]
    assert len(broker.orders) == 1  # the broker deduped the second request


def test_losing_refusal_run_raises_already_decided(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    aid = make_analysis(db_session, risk_status="VETOED")
    broker = FakeBroker()
    _race_inside_price_lookup(monkeypatch, lambda: submit_signal(_deps(db_session, broker), aid))
    with pytest.raises(AlreadyDecided):
        submit_signal(_deps(db_session, broker), aid)
    assert [r.submit_status for r in _rows(db_session, aid)] == ["refused_veto"]
    assert broker.calls == 0


def test_losing_rejection_run_raises_broker_rejected(
    db_session: Session, reviewed_signal: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both runs were rejected at attempt 1: the loser reports its own rejection
    (retry remains possible) rather than a store error."""
    broker = FakeBroker(fail_with=BrokerRejected("insufficient buying power"))

    def other() -> object:
        with pytest.raises(BrokerRejected):
            submit_signal(_deps(db_session, broker), reviewed_signal)
        return None

    _race_inside_price_lookup(monkeypatch, other)
    with pytest.raises(BrokerRejected):
        submit_signal(_deps(db_session, broker), reviewed_signal)
    assert [(r.attempt_no, r.submit_status) for r in _rows(db_session, reviewed_signal)] == [
        (1, "rejected")
    ]


# --------------------------------------------------------------------------- PostgreSQL, threads


@pytest.fixture(scope="module")
def pg_sessions() -> Iterator[sessionmaker[Session]]:
    """Sessions on a private, throwaway schema of the PG test database.

    The unique constraint under test comes from the ORM metadata (migration
    parity is proven in tests/paper/test_migration_roundtrip.py). A private
    schema keeps this test independent of the shared database's alembic
    revision and leaves no append-only rows behind.
    """
    url = _pg_url_or_skip()
    schema = f"submit_race_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, pool_size=4, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.mark.slow
def test_pg_two_threads_one_signal_one_row(
    pg_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pg_sessions() as setup:
        aid = make_analysis(setup)
        add_review(setup, aid)
        add_price(setup)

    # Both runs must have computed attempt 1 before either records anything.
    barrier = threading.Barrier(2, timeout=10)
    real = submit_mod.latest_adj_close_cents

    def synced(*args: object, **kwargs: object) -> int:
        barrier.wait()
        return real(*args, **kwargs)

    monkeypatch.setattr(submit_mod, "latest_adj_close_cents", synced)
    broker = LockedBroker()

    def run() -> object:
        with pg_sessions() as s:
            try:
                return submit_signal(_deps(s, broker), aid)
            except Exception as exc:  # noqa: BLE001 -- the outcome is what is asserted
                return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: run(), range(2)))

    records = [o for o in outcomes if isinstance(o, PaperTradeRecord)]
    errors = [o for o in outcomes if isinstance(o, Exception)]
    assert len(records) == 1, outcomes
    assert len(errors) == 1 and isinstance(errors[0], AlreadySubmitted), outcomes
    with pg_sessions() as check:
        rows = _rows(check, aid)
    assert [(r.attempt_no, r.submit_status) for r in rows] == [(1, "submitted")]
    assert len(broker.orders) == 1
