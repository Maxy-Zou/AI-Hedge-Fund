"""CLI: submit one reviewed signal to the paper broker (Phase 10 T7).

    submit_signal --episodic-id N [--policy PATH] [--database-url URL] [--dry-run] [--json]

Exit codes: 0 submitted (or dry-run), 2 refused (prints status + reason), 1 error.
Broker and session are dependency-injected for tests (the run_analysis pattern).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ai_hedge_fund.config import get_settings
from ai_hedge_fund.execution.broker import BrokerClient
from ai_hedge_fund.execution.decide import OrderPlan, Refusal
from ai_hedge_fund.execution.errors import ExecutionError
from ai_hedge_fund.execution.policy import (
    DEFAULT_EXECUTION_POLICY_PATH,
    compute_execution_policy_sha,
    load_execution_policy,
)
from ai_hedge_fund.execution.submit import SubmitDeps, submit_signal
from ai_hedge_fund.paper import PaperTradeRecord


def _default_session_factory(database_url: str | None) -> Callable[[], Session]:
    from ai_hedge_fund.db.session import get_engine, get_session_factory

    url = database_url or get_settings().database_url
    return get_session_factory(get_engine(url))


def _default_broker_factory(settings: Any) -> BrokerClient:
    from ai_hedge_fund.execution.alpaca import AlpacaPaperBroker

    return AlpacaPaperBroker.from_settings(settings)


def _main(
    argv: list[str] | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    broker_factory: Callable[[Any], BrokerClient] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Submit a reviewed signal to the paper broker.")
    parser.add_argument("--episodic-id", type=int, required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_EXECUTION_POLICY_PATH)
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    policy = load_execution_policy(args.policy)
    policy_sha = compute_execution_policy_sha(policy)
    factory = session_factory or _default_session_factory(args.database_url)

    session = factory()
    try:
        # The broker is only built when an order might actually be sent.
        broker = (broker_factory or _default_broker_factory)(get_settings())
        deps = SubmitDeps(db_session=session, broker=broker, policy=policy, policy_sha=policy_sha)
        result = submit_signal(deps, args.episodic_id, dry_run=args.dry_run)
    except ExecutionError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    return _report(result, as_json=args.as_json)


def _report(result: PaperTradeRecord | OrderPlan | Refusal, *, as_json: bool) -> int:
    if isinstance(result, OrderPlan):
        print(
            json.dumps(result.model_dump(), default=str)
            if as_json
            else f"DRY-RUN order: {result.side} {result.quantity}"
        )
        return 0
    if isinstance(result, Refusal):
        print(
            json.dumps(result.model_dump())
            if as_json
            else f"DRY-RUN refused: {result.status} ({result.reason})"
        )
        return 2
    # PaperTradeRecord
    if result.submit_status == "submitted":
        print(
            json.dumps(result.payload, default=str)
            if as_json
            else f"SUBMITTED: {result.broker_order_id} ({result.quantity} sh)"
        )
        return 0
    reason = result.payload.get("refusal_reason", "unknown")
    print(
        json.dumps(result.payload, default=str)
        if as_json
        else f"REFUSED: {result.submit_status} ({reason})"
    )
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
