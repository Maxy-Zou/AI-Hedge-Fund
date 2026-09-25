"""Phase 10 T7 -- submit_signal CLI (DI-injected broker + session; 09-PREMORTEM #21)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_hedge_fund.execution.errors import MissingBrokerCredentials
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


def test_dry_run_needs_no_broker_credentials(session_factory: Callable[[], Session]) -> None:
    """F1: --dry-run must not construct the broker, so missing creds is fine."""
    with session_factory() as s:
        aid = make_analysis(s)
        add_review(s, aid)
        add_price(s)

    def boom(_settings):
        raise MissingBrokerCredentials("ALPACA_PAPER_API_KEY is not set")

    rc = _main(
        ["--episodic-id", "1", "--policy", "config/execution_policy.yaml", "--dry-run"],
        session_factory=session_factory,
        broker_factory=boom,
    )
    assert rc == 0


def test_veto_refusal_needs_no_broker_credentials(session_factory: Callable[[], Session]) -> None:
    """F1: a VETOED signal is refused before the broker; missing creds must not block it."""
    with session_factory() as s:
        make_analysis(s, risk_status="VETOED")

    def boom(_settings):
        raise MissingBrokerCredentials("ALPACA_PAPER_API_KEY is not set")

    rc = _main(
        ["--episodic-id", "1", "--policy", "config/execution_policy.yaml"],
        session_factory=session_factory,
        broker_factory=boom,
    )
    assert rc == 2  # refused_veto recorded, no broker needed


def test_already_submitted_distinct_exit_code(session_factory: Callable[[], Session]) -> None:
    """F5: a benign already-handled re-run is not exit 1."""
    with session_factory() as s:
        aid = make_analysis(s)
        add_review(s, aid)
        add_price(s)
    broker = FakeBroker()
    first = _main(
        ["--episodic-id", "1", "--policy", "config/execution_policy.yaml"],
        session_factory=session_factory,
        broker_factory=lambda _s: broker,
    )
    assert first == 0
    again = _main(
        ["--episodic-id", "1", "--policy", "config/execution_policy.yaml"],
        session_factory=session_factory,
        broker_factory=lambda _s: FakeBroker(),
    )
    assert again == 3  # already handled, not an error


def test_unknown_id_exit_one(session_factory: Callable[[], Session]) -> None:
    rc = _run(
        ["--episodic-id", "999", "--policy", "config/execution_policy.yaml"],
        session_factory,
        FakeBroker(),
    )
    assert rc == 1


def test_lost_response_is_adopted_through_the_cli(
    session_factory: Callable[[], Session],
) -> None:
    """Round-2 re-review: adoption must work through the real CLI wrapper, not only
    when submit_signal is handed a FakeBroker directly."""
    with session_factory() as s:
        aid = make_analysis(s)
        add_review(s, aid)
        add_price(s)
    broker = FakeBroker(lose_response_once=True)
    argv = ["--episodic-id", "1", "--policy", "config/execution_policy.yaml"]
    assert _main(argv, session_factory=session_factory, broker_factory=lambda _s: broker) == 1
    assert _main(argv, session_factory=session_factory, broker_factory=lambda _s: broker) == 0
    with session_factory() as s:
        rows = query_paper_trades(s, as_of_date="2999-01-01", signal_id=1)
    assert [r.submit_status for r in rows] == ["submitted"] and len(broker.orders) == 1


def test_lazy_broker_implements_the_whole_broker_protocol() -> None:
    """The wrapper forgot a method once (round-2 re-review); keep it complete."""
    from ai_hedge_fund.execution.broker import BrokerClient
    from ai_hedge_fund.scripts.submit_signal import _LazyBroker

    wanted = {n for n in vars(BrokerClient) if not n.startswith("_")}
    assert wanted, "protocol has no public methods?"
    missing = {n for n in wanted if not callable(getattr(_LazyBroker, n, None))}
    assert not missing, f"_LazyBroker lacks {sorted(missing)}"


class _LoggingBroker(FakeBroker):
    """Logs on submit, as the real Alpaca adapter does (``paper_order_submitted``)."""

    def submit_order(self, req):  # noqa: ANN001, ANN201
        import structlog

        structlog.get_logger("test").info("paper_order_submitted", symbol=req.symbol)
        return super().submit_order(req)


def test_json_stdout_is_pure_json_even_when_the_broker_logs(
    session_factory: Callable[[], Session], capsys: pytest.CaptureFixture[str]
) -> None:
    """Found in Phase 11: unconfigured structlog printed log lines into --json stdout."""
    import json

    with session_factory() as s:
        aid = make_analysis(s)
        add_review(s, aid)
        add_price(s)
    rc = _run(
        ["--episodic-id", "1", "--policy", "config/execution_policy.yaml", "--json"],
        session_factory,
        _LoggingBroker(),
    )
    out, err = capsys.readouterr()
    assert rc == 0
    json.loads(out)  # raises if a log line leaked into stdout
    assert "paper_order_submitted" in err
