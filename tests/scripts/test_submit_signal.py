"""Phase 10 T7 -- submit_signal CLI (DI-injected broker + session; 09-PREMORTEM #21)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_hedge_fund.paper.recall import query_paper_trades
from ai_hedge_fund.scripts.submit_signal import _main
from tests.execution.conftest import add_price, add_review, make_analysis
from tests.execution.fakes import FakeBroker


@pytest.fixture()
def session_factory(sqlite_engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=sqlite_engine, expire_on_commit=False)


def _run(argv: list[str], factory: Callable[[], Session], broker: FakeBroker) -> int:
    return _main(
        argv,
        session_factory=factory,
        broker_factory=lambda _settings: broker,
    )


def test_submitted_exit_zero(session_factory: Callable[[], Session], sqlite_engine: Engine) -> None:
    with session_factory() as s:
        aid = make_analysis(s)
        add_review(s, aid)
        add_price(s)
    broker = FakeBroker()
    rc = _run(
        ["--episodic-id", "1", "--policy", "config/execution_policy.yaml"], session_factory, broker
    )
    assert rc == 0 and broker.calls == 1


def test_refusal_exit_two(session_factory: Callable[[], Session]) -> None:
    with session_factory() as s:
        make_analysis(s, risk_status="VETOED")
    broker = FakeBroker()
    rc = _run(
        ["--episodic-id", "1", "--policy", "config/execution_policy.yaml"], session_factory, broker
    )
    assert rc == 2 and broker.calls == 0


def test_dry_run_writes_nothing(session_factory: Callable[[], Session]) -> None:
    with session_factory() as s:
        aid = make_analysis(s)
        add_review(s, aid)
        add_price(s)
    broker = FakeBroker()
    rc = _run(
        ["--episodic-id", "1", "--policy", "config/execution_policy.yaml", "--dry-run"],
        session_factory,
        broker,
    )
    assert rc == 0 and broker.calls == 0
    with session_factory() as s:
        assert query_paper_trades(s, as_of_date="2999-01-01", signal_id=1) == []


def test_unknown_id_exit_one(session_factory: Callable[[], Session]) -> None:
    rc = _run(
        ["--episodic-id", "999", "--policy", "config/execution_policy.yaml"],
        session_factory,
        FakeBroker(),
    )
    assert rc == 1
