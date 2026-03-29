"""AI Washing signal loader — reads scores from shared PostgreSQL database.

Implements the integration boundary between the AI Washing Detector and the
backtesting framework. The database is the only coupling point — no Python
imports cross package boundaries (no 'from ai_washer import ...' anywhere here).

The loader executes a raw SQL JOIN query against the shared database, converts
the result into the SignalFrame contract, and raises SignalLoadError on all
failure modes (empty table, missing table, DB unreachable).

Usage::

    from sqlalchemy.orm import Session
    from fund_backtest.signal.loaders.ai_washing import AiWashingLoader, SignalLoadError

    loader = AiWashingLoader(session)
    try:
        signal_frame = loader.load()
    except SignalLoadError as exc:
        log.error("ai_washing_signal_unavailable", error=str(exc))
"""
from __future__ import annotations

import pandas as pd
import sqlalchemy.exc
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from fund_backtest.signal.types import SignalFrame

logger = structlog.get_logger(__name__)

# Table names as constants — makes schema changes explicit and avoids string duplication.
_SCORES_TABLE = "daily_scores"
_COMPANIES_TABLE = "companies"

# Raw SQL query — no ORM model import from ai_washer.
# scored_at is cast to date to strip the time component before pivoting.
# Results are ordered so pivot_table sees a consistent row order.
_SCORE_QUERY = text(
    f"""
    SELECT
        {_COMPANIES_TABLE}.ticker,
        {_SCORES_TABLE}.scored_at::date AS signal_date,
        {_SCORES_TABLE}.composite_score
    FROM {_SCORES_TABLE}
    JOIN {_COMPANIES_TABLE} ON {_SCORES_TABLE}.company_id = {_COMPANIES_TABLE}.id
    ORDER BY signal_date, ticker
    """
)


class SignalLoadError(RuntimeError):
    """Raised when AiWashingLoader cannot produce a valid SignalFrame.

    Covers all failure modes:
    - Empty table (no scores yet ingested)
    - Missing table or DB unreachable (OperationalError from SQLAlchemy)

    The message is always human-readable and safe to surface in logs.
    """


class AiWashingLoader:
    """Reads AI Washing Risk Scores from the shared database and returns a SignalFrame.

    The loader executes a single JOIN query, fetches all rows, and pivots them
    into the SignalFrame contract (DatetimeIndex index, ticker columns, float values).

    IMPORTANT: Do NOT apply shift(1) here. SignalAdapter.adapt() applies shift(1)
    as its final step. Adding another shift here would create a 2-day look-ahead lag.

    Args:
        session: SQLAlchemy Session connected to the shared database. The caller
                 is responsible for session lifecycle management.
    """

    def __init__(self, session: Session) -> None:
        """Initialise with an active SQLAlchemy session.

        Args:
            session: Open SQLAlchemy Session bound to the shared database.
        """
        self._session = session
        self._log = logger.bind(loader="ai_washing")

    def load(self) -> SignalFrame:
        """Execute the score query and return a SignalFrame.

        Fetches all rows from daily_scores JOIN companies, then pivots into a
        (dates x tickers) DataFrame with float values.

        Returns:
            SignalFrame with:
              - DatetimeIndex (tz-naive) of score dates
              - str ticker columns
              - float64 composite_score values (NaN where no score for that date/ticker)

        Raises:
            SignalLoadError: If the scores table is empty or the DB is unavailable.
        """
        try:
            result = self._session.execute(_SCORE_QUERY)
            rows = result.fetchall()
        except sqlalchemy.exc.OperationalError as exc:
            raise SignalLoadError(
                "AI Washing Detector scores table unavailable — "
                f"check that the database is reachable and migrations have run: {exc}"
            ) from exc

        if not rows:
            raise SignalLoadError(
                "AI Washing Detector scores table is empty — "
                "no scores have been ingested yet. "
                "Run the detector's scoring pipeline before backtesting."
            )

        self._log.info("ai_washing_loader_rows_fetched", row_count=len(rows))
        return self._pivot(rows)

    def _pivot(self, rows: list) -> SignalFrame:
        """Convert raw query rows into a SignalFrame.

        Args:
            rows: List of (ticker, signal_date, composite_score) tuples from the query.

        Returns:
            SignalFrame with DatetimeIndex (tz-naive), ticker columns, float64 values.
        """
        df = pd.DataFrame(rows, columns=["ticker", "signal_date", "composite_score"])

        # aggfunc="last" deduplicates multiple scores for the same (ticker, date):
        # the most recently inserted row wins. This matches the detector's upsert pattern.
        pivoted = df.pivot_table(
            index="signal_date",
            columns="ticker",
            values="composite_score",
            aggfunc="last",
        )

        # Cast DatetimeIndex to tz-naive — scored_at::date produces Python date objects,
        # which pd.DatetimeIndex wraps as tz-naive datetime64[ns] automatically.
        pivoted.index = pd.DatetimeIndex(pd.to_datetime(pivoted.index))

        # Remove the "ticker" column axis label to satisfy the SignalFrame contract.
        pivoted.columns.name = None

        # Cast SmallInteger composite_score to float64 (SignalFrame contract: float values).
        return pivoted.astype(float)
