"""Ingest paper-broker fills and dividend/corporate-action activity (Phase 11, D1).

    uv run python -m ai_hedge_fund.scripts.ingest_fills --since 2026-09-01 [--json]

Idempotent: re-running over the same window inserts nothing. Exit codes:
0 success; 1 a fill contradicted its trade (data needs attention) or another
error; 2 the broker call failed (auth, transport, or an unexpected response
shape -- nothing from the failing page is written).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ai_hedge_fund.config import get_settings
from ai_hedge_fund.execution.broker import BrokerClient
from ai_hedge_fund.execution.errors import ExecutionError
from ai_hedge_fund.logging import route_logs_to_stderr
from ai_hedge_fund.mtm.ingest import IngestResult, ingest_activities


def _default_session_factory(database_url: str | None) -> Callable[[], Session]:
    from ai_hedge_fund.db.session import get_engine, get_session_factory

    url = database_url or get_settings().database_url
    return get_session_factory(get_engine(url))


def _default_broker_factory(settings: Any) -> BrokerClient:
    from ai_hedge_fund.execution.alpaca import AlpacaPaperBroker

    return AlpacaPaperBroker.from_settings(settings)


def _report(result: IngestResult, *, as_json: bool) -> int:
    counts = dataclasses.asdict(result)
    if as_json:
        print(json.dumps(counts))
    else:
        print(" ".join(f"{k}={v}" for k, v in counts.items()))
    if result.fills_skipped_mismatch:
        print(
            "ERROR: some fills contradict their trade; see fill_trade_mismatch logs",
            file=sys.stderr,
        )
        return 1
    return 0


def _main(
    argv: list[str] | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    broker_factory: Callable[[Any], BrokerClient] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Ingest paper-broker fills and cash activity.")
    parser.add_argument("--since", type=date.fromisoformat, required=True, help="YYYY-MM-DD (NY)")
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    route_logs_to_stderr()  # keep stdout machine-readable for --json

    factory = session_factory or _default_session_factory(args.database_url)
    make_broker = broker_factory or _default_broker_factory
    session = factory()
    try:
        result = ingest_activities(session, make_broker(get_settings()), args.since)
    except ExecutionError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        session.close()
    return _report(result, as_json=args.as_json)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
