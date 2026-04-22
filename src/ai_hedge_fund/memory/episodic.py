"""Episodic memory schema + CSV seeder.

Mirrors :mod:`ai_hedge_fund.risk.portfolio` in shape: a Pydantic frozen
result model (:class:`EpisodicHit`) for read paths, and a CSV seeder for
fixtures. The recall query itself lives in :mod:`ai_hedge_fund.memory.recall`
so tests can import the temporal-filter contract without pulling in I/O.

Threat mitigation T-07-01 / T-07-02: SQLAlchemy ORM exclusively; no raw SQL
concatenation.
"""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory


class EpisodicHit(BaseModel):
    """Immutable view of a single ``episodic_memory`` row loaded for recall.

    Plan 07-03's ``memory_recall_node`` builds one of these per row and the
    pipeline passes the dump into ``state['episodic_hits']``. Frozen so
    downstream nodes cannot mutate hits (CLAUDE.md immutability).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    ticker: str = Field(min_length=1, max_length=10)
    sector: str
    record_type: str = Field(pattern=r"^(analysis|outcome)$")
    as_of_date: str  # ISO-8601
    signal_direction: str | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    outcome_pct: float | None = None
    linked_analysis_id: int | None = None
    policy_sha: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


def _normalise_as_of(value: str | date | datetime) -> datetime:
    """Convert loose date/datetime/string inputs to a UTC datetime.

    Mirrors the helper in :mod:`ai_hedge_fund.risk.portfolio`. Naive
    datetimes are treated as UTC. Plain dates become midnight UTC. Strings
    are parsed via :func:`datetime.fromisoformat` (ISO-8601 only).
    """
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def seed_episodic_from_csv(db_session: Session, csv_path: str | Path) -> int:
    """Seed ``episodic_memory`` from a developer-owned CSV fixture.

    Expected header::

        ticker,sector,record_type,as_of_date,signal_direction,confidence,outcome_pct,policy_sha

    Blank ``confidence`` / ``outcome_pct`` cells become ``None``;
    ``record_type`` is preserved verbatim; ``policy_sha`` is optional.
    Returns the number of rows inserted.
    """
    path = Path(csv_path)
    rows: list[EpisodicMemory] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for record in reader:
            outcome_raw = record.get("outcome_pct", "").strip()
            confidence_raw = record.get("confidence", "").strip()
            signal_raw = record.get("signal_direction", "").strip()
            policy_raw = record.get("policy_sha", "").strip()
            rows.append(
                EpisodicMemory(
                    ticker=record["ticker"].strip(),
                    sector=record["sector"].strip(),
                    record_type=record["record_type"].strip(),
                    signal_direction=signal_raw or None,
                    confidence=int(confidence_raw) if confidence_raw else None,
                    outcome_pct=float(outcome_raw) if outcome_raw else None,
                    policy_sha=policy_raw or None,
                    payload={"schema_version": 1, "source": "csv_seed"},
                    as_of_date=_normalise_as_of(record["as_of_date"].strip()),
                )
            )
    db_session.add_all(rows)
    db_session.commit()
    return len(rows)
