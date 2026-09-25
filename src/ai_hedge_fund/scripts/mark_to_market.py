"""End-of-day mark-to-market for the paper book (Phase 11, MTM-01..04).

    uv run python -m ai_hedge_fund.scripts.mark_to_market [--date YYYY-MM-DD] [--dry-run] [--json]

Run ``ingest_fills`` first so the day's fills and dividends are in the ledger.
``--date`` defaults to the last completed trading day. Re-running a date inserts
nothing. Exit codes: 0 success (including "everything skipped" -- see the
skipped_* fields); 3 the date has not closed yet (nothing written); 1 any other
error, e.g. a concurrent run (the batch was rolled back).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ai_hedge_fund.config import get_settings
from ai_hedge_fund.logging import route_logs_to_stderr
from ai_hedge_fund.mtm.errors import IncompleteTradingDay, MtmError
from ai_hedge_fund.mtm.job import JobResult, last_completed_trading_day, run_mark_to_market
from ai_hedge_fund.mtm.policy import DEFAULT_MTM_POLICY_PATH, load_mtm_policy


def _default_session_factory(database_url: str | None) -> Callable[[], Session]:
    from ai_hedge_fund.db.session import get_engine, get_session_factory

    url = database_url or get_settings().database_url
    return get_session_factory(get_engine(url))


def _report(result: JobResult, *, dry_run: bool, as_json: bool) -> None:
    summary = {
        "pnl_date": result.pnl_date.isoformat(),
        "dry_run": dry_run,
        "inserted": result.inserted,
        "skipped_existing": result.skipped_existing,
        "skipped_no_price": list(result.skipped_no_price),
        "skipped_corporate_action": list(result.skipped_corporate_action),
        "skipped_oversold": list(result.skipped_oversold),
    }
    if dry_run:
        summary["rows"] = [r.model_dump(mode="json") for r in result.rows]
    if as_json:
        print(json.dumps(summary))
        return
    for key, value in summary.items():
        if key != "rows":
            print(f"{key}: {value}")
    for row in result.rows if dry_run else ():
        print(f"  signal {row.signal_id} {row.ticker}: total {row.total_pnl_cents} cents")


def _main(
    argv: list[str] | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    now_factory: Callable[[], datetime] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Mark the paper book to market for one day.")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="YYYY-MM-DD")
    parser.add_argument("--policy", type=Path, default=DEFAULT_MTM_POLICY_PATH)
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    route_logs_to_stderr()  # keep stdout machine-readable for --json

    policy = load_mtm_policy(args.policy)
    now = (now_factory or (lambda: datetime.now(UTC)))()
    pnl_date = args.date or last_completed_trading_day(now, policy)
    session = (session_factory or _default_session_factory(args.database_url))()
    try:
        result = run_mark_to_market(session, pnl_date, policy, now=now, dry_run=args.dry_run)
    except IncompleteTradingDay as exc:
        print(f"NOT YET: IncompleteTradingDay: {exc}", file=sys.stderr)
        return 3
    except MtmError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()
    _report(result, dry_run=args.dry_run, as_json=args.as_json)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
