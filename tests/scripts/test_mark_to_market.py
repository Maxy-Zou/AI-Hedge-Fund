"""Phase 11 T7 -- mark_to_market CLI (DI-injected session and clock; 11-SPEC s6)."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_hedge_fund.mtm.job import last_completed_trading_day
from ai_hedge_fund.mtm.policy import load_mtm_policy
from ai_hedge_fund.mtm.store import query_pnl_rows
from ai_hedge_fund.scripts.mark_to_market import _main
from tests.mtm.test_job import NOW, held, price

POLICY = load_mtm_policy()


@pytest.fixture()
def session_factory(sqlite_engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=sqlite_engine, expire_on_commit=False)


def _run(argv: list[str], factory: Callable[[], Session], now: datetime = NOW) -> int:
    return _main(argv, session_factory=factory, now_factory=lambda: now)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 9, 3, 21, 0, tzinfo=UTC), date(2026, 9, 3)),  # Thu 17:00 ET
        (datetime(2026, 9, 3, 19, 0, tzinfo=UTC), date(2026, 9, 2)),  # Thu 15:00 ET
        (datetime(2026, 9, 5, 15, 0, tzinfo=UTC), date(2026, 9, 4)),  # Saturday
        (datetime(2026, 9, 7, 14, 0, tzinfo=UTC), date(2026, 9, 4)),  # Monday morning
    ],
    ids=["after-close", "intraday", "weekend", "monday-morning"],
)
def test_last_completed_trading_day(now: datetime, expected: date) -> None:
    assert last_completed_trading_day(now, POLICY) == expected


def test_marks_and_reports_json(
    session_factory: Callable[[], Session], capsys: pytest.CaptureFixture[str]
) -> None:
    with session_factory() as s:
        held(s)
        price(s, 3, 10_500)
    rc = _run(["--date", "2026-09-03", "--json"], session_factory)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["inserted"] == 1 and out["pnl_date"] == "2026-09-03"
    assert out["skipped_no_price"] == []


def test_defaults_to_last_completed_day(session_factory: Callable[[], Session]) -> None:
    with session_factory() as s:
        held(s)
        price(s, 4, 10_500)
    rc = _run([], session_factory, now=datetime(2026, 9, 7, 14, 0, tzinfo=UTC))
    assert rc == 0
    with session_factory() as s:
        assert [r.pnl_date for r in query_pnl_rows(s)] == ["2026-09-04"]


def test_dry_run_writes_nothing(
    session_factory: Callable[[], Session], capsys: pytest.CaptureFixture[str]
) -> None:
    """11-PREMORTEM #36."""
    with session_factory() as s:
        held(s)
        price(s, 3, 10_500)
    rc = _run(["--date", "2026-09-03", "--dry-run", "--json"], session_factory)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True and len(out["rows"]) == 1
    with session_factory() as s:
        assert query_pnl_rows(s) == []


def test_incomplete_day_exits_three(
    session_factory: Callable[[], Session], capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _run(["--date", "2026-09-03"], session_factory, now=datetime(2026, 9, 3, 18, tzinfo=UTC))
    assert rc == 3
    assert "IncompleteTradingDay" in capsys.readouterr().err


def test_bad_date_is_argparse_error(session_factory: Callable[[], Session]) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(["--date", "Sept 3"], session_factory)
    assert exc.value.code == 2


def test_module_entry_point_runs() -> None:
    """11-PREMORTEM #35: the real entry point imports (no circular import via graph)."""
    proc = subprocess.run(
        [sys.executable, "-m", "ai_hedge_fund.scripts.mark_to_market", "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--dry-run" in proc.stdout
