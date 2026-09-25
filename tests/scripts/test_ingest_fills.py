"""Phase 11 T4 -- ingest_fills CLI (DI-injected broker + session; 11-SPEC s4)."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_hedge_fund.execution.errors import BrokerAuthError, UnexpectedBrokerResponse
from ai_hedge_fund.scripts.ingest_fills import _main
from tests.execution.fakes import FakeBroker
from tests.mtm.test_ingest import _cash, _fill, _trade


@pytest.fixture()
def session_factory(sqlite_engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=sqlite_engine, expire_on_commit=False)


def _run(argv: list[str], factory: Callable[[], Session], broker: FakeBroker) -> int:
    return _main(argv, session_factory=factory, broker_factory=lambda _settings: broker)


class _Failing(FakeBroker):
    def __init__(self, exc: Exception) -> None:
        super().__init__()
        self._exc = exc

    def list_activities(self, types, since):  # noqa: ANN001, ANN202
        raise self._exc


def test_success_exit_zero_and_json_counts(
    session_factory: Callable[[], Session], capsys: pytest.CaptureFixture[str]
) -> None:
    with session_factory() as s:
        _trade(s, "ord-1")
    broker = FakeBroker()
    broker.activities.extend([_fill(1), _cash(1)])
    rc = _run(["--since", "2026-09-01", "--json"], session_factory, broker)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fills_inserted"] == 1 and out["cash_inserted"] == 1


def test_rerun_is_zero_and_inserts_nothing(
    session_factory: Callable[[], Session], capsys: pytest.CaptureFixture[str]
) -> None:
    with session_factory() as s:
        _trade(s, "ord-1")
    broker = FakeBroker()
    broker.activities.append(_fill(1))
    assert _run(["--since", "2026-09-01"], session_factory, broker) == 0
    capsys.readouterr()
    assert _run(["--since", "2026-09-01", "--json"], session_factory, broker) == 0
    assert json.loads(capsys.readouterr().out)["fills_inserted"] == 0


def test_mismatched_fill_exits_one(session_factory: Callable[[], Session]) -> None:
    """Data corruption is not a quiet success."""
    with session_factory() as s:
        _trade(s, "ord-1")
    broker = FakeBroker()
    broker.activities.append(_fill(1, side="sell"))
    assert _run(["--since", "2026-09-01"], session_factory, broker) == 1


def test_rejected_own_fill_exits_one(session_factory: Callable[[], Session]) -> None:
    from ai_hedge_fund.execution.broker import RejectedActivity

    with session_factory() as s:
        _trade(s, "ord-1")
    broker = FakeBroker()
    broker.rejected.append(RejectedActivity("r1", "FILL", "ord-1", "fractional qty 0.5", {}))
    assert _run(["--since", "2026-09-01"], session_factory, broker) == 1


@pytest.mark.parametrize(
    "exc", [BrokerAuthError("HTTP 401"), UnexpectedBrokerResponse("drift")], ids=["auth", "shape"]
)
def test_broker_error_exits_two(
    session_factory: Callable[[], Session], exc: Exception, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _run(["--since", "2026-09-01"], session_factory, _Failing(exc))
    assert rc == 2
    assert type(exc).__name__ in capsys.readouterr().err


@pytest.mark.parametrize("argv", [[], ["--since", "09/01/2026"]], ids=["missing", "not-iso"])
def test_since_is_required_iso_date(
    argv: list[str], session_factory: Callable[[], Session]
) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(argv, session_factory, FakeBroker())
    assert exc.value.code == 2
