"""Integration tests for the AI Washing Detector pipeline.

Tests run against a real PostgreSQL testcontainer (via conftest.py fixtures).
Exercises AiWashingLoader -> SignalAdapter -> PortfolioSimulator -> MetricsEngine
without any mocks — the full pipeline against a real database.

Schema note: The testcontainer has fund_backtest Alembic migrations applied.
The AI Washing Detector tables (companies, daily_scores) are created inline
using simplified DDL (no partitioning) since detector migrations are not run.

Run with: uv run pytest tests/integration/test_ai_washing_integration.py -v
"""
from __future__ import annotations

import math
import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from fund_backtest.metrics.engine import MetricsEngine
from fund_backtest.signal.adapter import SignalAdapter
from fund_backtest.signal.loaders import AiWashingLoader, SignalLoadError
from fund_backtest.simulator.engine import PortfolioSimulator

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Schema setup helpers
# ---------------------------------------------------------------------------

_CREATE_COMPANIES_DDL = """
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR NOT NULL UNIQUE
)
"""

_CREATE_DAILY_SCORES_DDL = """
CREATE TABLE IF NOT EXISTS daily_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id),
    scored_at TIMESTAMP WITH TIME ZONE NOT NULL,
    composite_score SMALLINT NOT NULL
)
"""

_DROP_DAILY_SCORES_DDL = "DROP TABLE IF EXISTS daily_scores"
_DROP_COMPANIES_DDL = "DROP TABLE IF EXISTS companies"


def _create_schema(session) -> None:
    """Create simplified AI Washing Detector tables in the testcontainer."""
    session.execute(text(_CREATE_COMPANIES_DDL))
    session.execute(text(_CREATE_DAILY_SCORES_DDL))
    session.commit()


def _drop_schema(session) -> None:
    """Drop AI Washing Detector tables to isolate tests from each other."""
    session.execute(text(_DROP_DAILY_SCORES_DDL))
    session.execute(text(_DROP_COMPANIES_DDL))
    session.commit()


def _seed_scores(
    session,
    tickers: list[str],
    n_days: int,
    base_score: int = 60,
    start_date: date = date(2024, 1, 2),
) -> None:
    """Seed companies + daily_scores rows for given tickers and day count.

    Uses sequential calendar days (not business days) for simplicity.
    Each ticker gets one score per day starting from start_date.

    Args:
        session: SQLAlchemy Session connected to the testcontainer.
        tickers: Ticker symbols to seed.
        n_days: Number of days of scores to insert.
        base_score: composite_score value for all rows.
        start_date: First scored_at date (inclusive).
    """
    company_ids: dict[str, uuid.UUID] = {}
    for ticker in tickers:
        cid = uuid.uuid4()
        session.execute(
            text(
                "INSERT INTO companies (id, ticker) VALUES (:id, :ticker)"
                " ON CONFLICT (ticker) DO NOTHING"
            ),
            {"id": cid, "ticker": ticker},
        )
        company_ids[ticker] = cid
    session.commit()

    for i in range(n_days):
        scored_day = start_date + timedelta(days=i)
        for ticker, cid in company_ids.items():
            session.execute(
                text(
                    "INSERT INTO daily_scores (id, company_id, scored_at, composite_score)"
                    " VALUES (:id, :cid, :scored_at, :score)"
                ),
                {
                    "id": uuid.uuid4(),
                    "cid": cid,
                    "scored_at": f"{scored_day}T10:00:00+00:00",
                    "score": base_score,
                },
            )
    session.commit()


# ---------------------------------------------------------------------------
# Per-test cleanup fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_ai_washing_tables(db_session):
    """Drop and recreate AI Washing tables before each test.

    Ensures test isolation — each test sees a fresh schema since
    daily_scores inserts are committed (conftest rollback cannot undo them).
    """
    _drop_schema(db_session)
    _create_schema(db_session)
    yield
    _drop_schema(db_session)


# ---------------------------------------------------------------------------
# Test 1: Loader returns correct SignalFrame from seeded data
# ---------------------------------------------------------------------------


def test_loader_returns_signal_frame_from_real_db(db_session):
    """AiWashingLoader.load() returns a (3, 2) SignalFrame from 2 tickers x 3 days."""
    _seed_scores(db_session, tickers=["AAPL", "MSFT"], n_days=3, base_score=65)

    loader = AiWashingLoader(db_session)
    signal_frame = loader.load()

    # Shape: 3 dates x 2 tickers
    assert signal_frame.shape == (3, 2), (
        f"Expected shape (3, 2), got {signal_frame.shape}"
    )

    # All values must be float
    assert signal_frame.dtypes.apply(lambda dt: dt == float or dt.kind == "f").all(), (
        f"Expected all float columns, got dtypes: {signal_frame.dtypes.tolist()}"
    )

    # Index must be DatetimeIndex
    assert isinstance(signal_frame.index, pd.DatetimeIndex), (
        f"Expected DatetimeIndex, got {type(signal_frame.index)}"
    )

    # Columns should be ticker names
    assert set(signal_frame.columns) == {"AAPL", "MSFT"}


# ---------------------------------------------------------------------------
# Test 2: Loader raises SignalLoadError on empty daily_scores table
# ---------------------------------------------------------------------------


def test_loader_raises_on_empty_table(db_session):
    """AiWashingLoader.load() raises SignalLoadError when daily_scores is empty."""
    # Seed only companies — no daily_scores rows
    cid = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO companies (id, ticker) VALUES (:id, :ticker)"),
        {"id": cid, "ticker": "AAPL"},
    )
    db_session.commit()

    loader = AiWashingLoader(db_session)

    with pytest.raises(SignalLoadError) as exc_info:
        loader.load()

    assert "empty" in str(exc_info.value).lower(), (
        f"Expected 'empty' in error message, got: {exc_info.value}"
    )


# ---------------------------------------------------------------------------
# Test 3: Full pipeline — load -> adapt -> simulate -> metrics
# ---------------------------------------------------------------------------


def test_full_pipeline_load_adapt_simulate_metrics(db_session):
    """Full pipeline (load->adapt->simulate->metrics) completes without exceptions.

    Seeds 5 tickers x 60 sequential days of scores. Builds a synthetic
    price_frame (constant $100 price) aligned to the signal dates and tickers.
    Runs all pipeline stages and asserts MetricsBundle fields are finite floats.
    """
    tickers = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
    n_days = 60
    _seed_scores(db_session, tickers=tickers, n_days=n_days, base_score=60)

    # Stage 1: Load signal
    loader = AiWashingLoader(db_session)
    signal_frame = loader.load()

    assert signal_frame.shape[0] == n_days, (
        f"Expected {n_days} date rows, got {signal_frame.shape[0]}"
    )
    assert signal_frame.shape[1] == len(tickers), (
        f"Expected {len(tickers)} ticker columns, got {signal_frame.shape[1]}"
    )

    # Build synthetic price_frame aligned to signal dates and tickers.
    # Constant $100 price with tiny random noise so pct_change() is non-zero.
    # Using a small noise ensures the simulator has non-trivial returns to work with.
    rng = np.random.default_rng(seed=42)
    noise = rng.normal(loc=0, scale=0.005, size=signal_frame.shape)
    close_prices = 100.0 * (1 + noise)
    price_frame = pd.DataFrame(
        close_prices,
        index=signal_frame.index,
        columns=signal_frame.columns,
    )

    # Stage 2: Adapt signal to weights
    weight_frame = SignalAdapter().adapt(signal_frame)

    # Stage 3: Simulate portfolio
    portfolio_result = PortfolioSimulator().simulate(weight_frame, price_frame)

    # net_returns must be non-empty
    assert len(portfolio_result.net_returns) > 0, "net_returns must be non-empty"

    # Stage 4: Compute metrics
    bundle = MetricsEngine().compute(portfolio_result)

    # All scalar metrics must be finite floats
    assert math.isfinite(bundle.sharpe), f"sharpe not finite: {bundle.sharpe}"
    assert math.isfinite(bundle.cagr), f"cagr not finite: {bundle.cagr}"
    assert math.isfinite(bundle.max_drawdown), f"max_drawdown not finite: {bundle.max_drawdown}"
    assert math.isfinite(bundle.sortino), f"sortino not finite: {bundle.sortino}"

    # max_drawdown convention: must be <= 0
    assert bundle.max_drawdown <= 0.0, (
        f"max_drawdown should be <= 0, got {bundle.max_drawdown}"
    )
