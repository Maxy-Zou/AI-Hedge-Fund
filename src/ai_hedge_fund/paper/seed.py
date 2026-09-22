"""CSV seeders for the paper-trading ledger (test fixtures, not a CLI).

Both seeders route every row through the real writers in
:mod:`ai_hedge_fund.paper.store`, so seeded data passes exactly the same
validation as production writes and inherits their typed errors.

Signal resolution is by exact ``(ticker, as_of_date, record_type='analysis')``.
``episodic_memory`` permits duplicate analyses by design, so zero matches raise
:class:`SignalNotFound` and more than one raise :class:`AmbiguousSignal` --
the seeder never silently picks one (09-PREMORTEM.md #16).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import EpisodicMemory, PaperTrade
from ai_hedge_fund.paper.errors import (
    AmbiguousSignal,
    SeedFormatError,
    SignalNotFound,
    TradeNotFound,
)
from ai_hedge_fund.paper.records import NewPaperFill, NewPaperTrade
from ai_hedge_fund.paper.store import insert_paper_fill, insert_paper_trade

TRADE_COLUMNS = (
    "signal_ticker,signal_as_of_date,attempt_no,ticker,side,order_type,quantity,"
    "limit_price_cents,submit_status,broker_order_id,risk_status_at_submit,"
    "policy_sha,review_policy_sha,as_of_date"
)
FILL_COLUMNS = "broker_order_id,broker_fill_id,filled_qty,fill_price_cents,filled_at,as_of_date"


def _blank_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _opt_int(value: str | None) -> int | None:
    cleaned = _blank_to_none(value)
    return int(cleaned) if cleaned is not None else None


def _reader(fh: Any, path: Path, expected: str) -> csv.DictReader:
    """Validate the header before trusting a single cell (CLAUDE.md: validate at boundaries)."""
    reader = csv.DictReader(fh)
    if reader.fieldnames != expected.split(","):
        raise SeedFormatError(
            f"{path.name}: expected header {expected!r}, got {reader.fieldnames!r}"
        )
    return reader


def resolve_signal_id(db_session: Session, ticker: str, as_of_date: str) -> int:
    """Return the id of the single analysis row for ``(ticker, as_of_date)``."""
    rows = (
        db_session.query(EpisodicMemory.id)
        .filter(EpisodicMemory.ticker == ticker)
        .filter(EpisodicMemory.record_type == "analysis")
        .filter(EpisodicMemory.as_of_date == normalise_as_of(as_of_date))
        .all()
    )
    if not rows:
        raise SignalNotFound(f"no analysis row for {ticker} @ {as_of_date}")
    if len(rows) > 1:
        raise AmbiguousSignal(f"{len(rows)} analysis rows for {ticker} @ {as_of_date}")
    return int(rows[0][0])


def _resolve_trade_id(db_session: Session, broker_order_id: str) -> int:
    row = db_session.query(PaperTrade.id).filter_by(broker_order_id=broker_order_id).one_or_none()
    if row is None:
        raise TradeNotFound(f"no paper_trades row with broker_order_id={broker_order_id!r}")
    return int(row[0])


def seed_paper_trades_from_csv(db_session: Session, csv_path: str | Path) -> int:
    """Seed ``paper_trades`` from a CSV with header ``TRADE_COLUMNS``. Returns rows inserted."""
    inserted = 0
    path = Path(csv_path)
    with path.open(newline="", encoding="utf-8") as fh:
        for record in _reader(fh, path, TRADE_COLUMNS):
            signal_id = resolve_signal_id(
                db_session, record["signal_ticker"].strip(), record["signal_as_of_date"].strip()
            )
            attempt_no = _opt_int(record.get("attempt_no"))
            fields: dict[str, Any] = {
                "signal_id": signal_id,
                # Blank -> 1. An explicit 0 is passed through so NewPaperTrade rejects it.
                "attempt_no": 1 if attempt_no is None else attempt_no,
                "ticker": record["ticker"].strip(),
                "side": record["side"].strip(),
                "order_type": record["order_type"].strip(),
                "quantity": int(record["quantity"]),
                "limit_price_cents": _opt_int(record.get("limit_price_cents")),
                "submit_status": record["submit_status"].strip(),
                "broker_order_id": _blank_to_none(record.get("broker_order_id")),
                "risk_status_at_submit": record["risk_status_at_submit"].strip(),
                "policy_sha": record["policy_sha"].strip(),
                "review_policy_sha": record["review_policy_sha"].strip(),
                "as_of_date": record["as_of_date"].strip(),
                "payload": {"schema_version": 1, "source": "csv_seed"},
            }
            insert_paper_trade(db_session, NewPaperTrade(**fields))
            inserted += 1
    return inserted


def seed_paper_fills_from_csv(db_session: Session, csv_path: str | Path) -> int:
    """Seed ``paper_fills`` from a CSV with header ``FILL_COLUMNS``. Returns rows inserted."""
    inserted = 0
    path = Path(csv_path)
    with path.open(newline="", encoding="utf-8") as fh:
        for record in _reader(fh, path, FILL_COLUMNS):
            trade_id = _resolve_trade_id(db_session, record["broker_order_id"].strip())
            insert_paper_fill(
                db_session,
                NewPaperFill(
                    trade_id=trade_id,
                    broker_fill_id=record["broker_fill_id"].strip(),
                    filled_qty=int(record["filled_qty"]),
                    fill_price_cents=int(record["fill_price_cents"]),
                    filled_at=normalise_as_of(record["filled_at"].strip()),
                    as_of_date=record["as_of_date"].strip(),
                    payload={"schema_version": 1, "source": "csv_seed"},
                ),
            )
            inserted += 1
    return inserted
