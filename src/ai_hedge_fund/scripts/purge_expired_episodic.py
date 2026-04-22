"""90-day retention sweep for ``episodic_memory`` (MEM-01).

Deletes rows where ``as_of_date < today - retention_days``. Idempotent:
running twice in a row returns 0 on the second call (no rows left).

Designed to be cron-invoked once daily. NOT wired into the live pipeline
(07-RESEARCH.md Anti-Pattern: read-time retention filter leaks retention
semantics into every consumer).

Threat mitigation T-07-02: SQLAlchemy ORM ``delete()`` exclusively; no
raw SQL. Mitigation T-07-04: append-only invariant preserved — retention
is a *delete* operation, never an UPDATE.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
from typing import cast

import structlog
from sqlalchemy import delete
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory

logger = structlog.get_logger(__name__)


def purge_expired(
    db_session: Session,
    *,
    retention_days: int = 90,
    today: date | None = None,
) -> int:
    """Delete ``episodic_memory`` rows older than ``retention_days``.

    Args:
        db_session: Open SQLAlchemy session.
        retention_days: Days to retain from ``today`` (inclusive). Defaults
            to 90. Must be ``>= 0``.
        today: Override "today" for tests. Defaults to :func:`date.today`.

    Returns:
        Number of rows deleted.

    Raises:
        ValueError: ``retention_days`` is negative.
    """
    if retention_days < 0:
        raise ValueError(f"retention_days must be >= 0; got {retention_days}")
    anchor = today or date.today()
    cutoff = datetime(anchor.year, anchor.month, anchor.day, tzinfo=UTC) - timedelta(
        days=retention_days
    )
    result = db_session.execute(delete(EpisodicMemory).where(EpisodicMemory.as_of_date < cutoff))
    db_session.commit()
    deleted = cast(int, result.rowcount or 0)
    logger.info(
        "episodic_retention_sweep",
        cutoff=cutoff.isoformat(),
        retention_days=retention_days,
        deleted=deleted,
    )
    return deleted


def _main() -> int:  # pragma: no cover - CLI entry
    from ai_hedge_fund.config import AppSettings
    from ai_hedge_fund.db.session import get_engine, get_session_factory

    parser = argparse.ArgumentParser(description="Purge expired episodic_memory rows.")
    parser.add_argument("--retention-days", type=int, default=90)
    parser.add_argument("--database-url", type=str, default=None)
    args = parser.parse_args()

    settings = AppSettings()
    url = args.database_url or settings.database_url
    engine = get_engine(url)
    factory = get_session_factory(engine)
    session = factory()
    try:
        count = purge_expired(session, retention_days=args.retention_days)
        print(f"deleted {count} rows")
        return 0
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(_main())
