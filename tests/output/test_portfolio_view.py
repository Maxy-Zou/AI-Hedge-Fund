"""Plan 08-02 Task 1: query_portfolio_view tests (SIG-02).

Covers the SIG-02 contract for the portfolio view query over
``episodic_memory``:

    - ranking (confidence DESC within sector),
    - grouping (by sector),
    - latest-per-ticker,
    - freshness (no cache; append-only truth),
    - temporal cutoff (Pitfall 2 regression),
    - sector filter,
    - record_type='analysis' exclusivity,
    - ``limit_per_sector`` DoS cap,
    - entry-shape contract,
    - anti-Pitfall-C source-grep regression (no ``@lru_cache``).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.output.portfolio_view import query_portfolio_view


def _insert(
    session: Session,
    *,
    ticker: str,
    sector: str,
    confidence: int,
    as_of: str,
    record_type: str = "analysis",
    signal_direction: str = "long",
    policy_sha: str = "a" * 64,
    payload: dict | None = None,
) -> int:
    """Seed a single ``episodic_memory`` row and return its primary key."""
    row = EpisodicMemory(
        ticker=ticker,
        sector=sector,
        record_type=record_type,
        signal_direction=signal_direction,
        confidence=confidence,
        outcome_pct=None,
        linked_analysis_id=None,
        policy_sha=policy_sha,
        as_of_date=date.fromisoformat(as_of),
        payload=payload or {"thesis": {"bull_case": f"{ticker} bull case"}},
    )
    session.add(row)
    session.flush()
    return row.id


# Note: ``portfolio_db_session`` is re-exported from tests.memory.conftest via
# tests/output/conftest.py (Plan 08-00). It provides an in-memory SQLite session
# with Base.metadata.create_all() already invoked.


def test_empty_db_returns_empty_dict(portfolio_db_session: Session) -> None:
    """Test 1: empty DB -> empty dict."""
    assert query_portfolio_view(portfolio_db_session, as_of_date="2026-04-20") == {}


def test_ranks_by_conviction_desc(portfolio_db_session: Session) -> None:
    """Test 2: within a sector, entries are ranked by conviction DESC."""
    _insert(
        portfolio_db_session,
        ticker="AAA",
        sector="Technology",
        confidence=30,
        as_of="2026-04-20",
    )
    _insert(
        portfolio_db_session,
        ticker="BBB",
        sector="Technology",
        confidence=80,
        as_of="2026-04-20",
    )
    _insert(
        portfolio_db_session,
        ticker="CCC",
        sector="Technology",
        confidence=50,
        as_of="2026-04-20",
    )
    portfolio_db_session.commit()

    view = query_portfolio_view(portfolio_db_session, as_of_date="2026-04-20")
    assert [e["ticker"] for e in view["Technology"]] == ["BBB", "CCC", "AAA"]


def test_groups_by_sector(portfolio_db_session: Session) -> None:
    """Test 3: results are keyed by sector."""
    _insert(
        portfolio_db_session,
        ticker="AAPL",
        sector="Technology",
        confidence=80,
        as_of="2026-04-20",
    )
    _insert(
        portfolio_db_session,
        ticker="PFE",
        sector="Healthcare",
        confidence=60,
        as_of="2026-04-20",
    )
    portfolio_db_session.commit()

    view = query_portfolio_view(portfolio_db_session, as_of_date="2026-04-20")
    assert set(view.keys()) == {"Technology", "Healthcare"}


def test_latest_per_ticker_only(portfolio_db_session: Session) -> None:
    """Test 4: only the latest analysis row per ticker is surfaced."""
    _insert(
        portfolio_db_session,
        ticker="AAPL",
        sector="Technology",
        confidence=70,
        as_of="2026-04-15",
    )
    _insert(
        portfolio_db_session,
        ticker="AAPL",
        sector="Technology",
        confidence=80,
        as_of="2026-04-19",
    )
    portfolio_db_session.commit()

    view = query_portfolio_view(portfolio_db_session, as_of_date="2026-04-20")
    aapl_entries = [e for e in view["Technology"] if e["ticker"] == "AAPL"]
    assert len(aapl_entries) == 1
    assert aapl_entries[0]["conviction"] == 80
    assert aapl_entries[0]["as_of_date"] == "2026-04-19"


def test_freshness_after_new_insert_no_cache(portfolio_db_session: Session) -> None:
    """Test 5: SIG-02 freshness invariant (Pitfall C).

    Append-only truth IS the cache -- a new analysis row written between two
    calls MUST appear on the second call without any explicit refresh.
    """
    _insert(
        portfolio_db_session,
        ticker="AAPL",
        sector="Technology",
        confidence=70,
        as_of="2026-04-20",
    )
    portfolio_db_session.commit()

    v1 = query_portfolio_view(portfolio_db_session, as_of_date="2026-04-20")
    assert [e["ticker"] for e in v1.get("Technology", [])] == ["AAPL"]

    _insert(
        portfolio_db_session,
        ticker="MSFT",
        sector="Technology",
        confidence=80,
        as_of="2026-04-20",
    )
    portfolio_db_session.commit()

    v2 = query_portfolio_view(portfolio_db_session, as_of_date="2026-04-20")
    tickers = {e["ticker"] for e in v2["Technology"]}
    assert tickers == {"AAPL", "MSFT"}


def test_temporal_cutoff_excludes_future(portfolio_db_session: Session) -> None:
    """Test 6: Pitfall 2 regression -- future-dated rows NEVER leak."""
    _insert(
        portfolio_db_session,
        ticker="AAPL",
        sector="Technology",
        confidence=70,
        as_of="2026-04-15",
    )
    _insert(
        portfolio_db_session,
        ticker="FUTUREX",
        sector="Technology",
        confidence=99,
        as_of="2099-01-01",
    )
    portfolio_db_session.commit()

    view = query_portfolio_view(portfolio_db_session, as_of_date="2026-04-20")
    tickers = {e["ticker"] for s in view.values() for e in s}
    assert "FUTUREX" not in tickers
    assert "AAPL" in tickers


def test_sector_filter(portfolio_db_session: Session) -> None:
    """Test 7: sector filter narrows the result set."""
    _insert(
        portfolio_db_session,
        ticker="AAPL",
        sector="Technology",
        confidence=80,
        as_of="2026-04-20",
    )
    _insert(
        portfolio_db_session,
        ticker="PFE",
        sector="Healthcare",
        confidence=60,
        as_of="2026-04-20",
    )
    portfolio_db_session.commit()

    view = query_portfolio_view(
        portfolio_db_session,
        as_of_date="2026-04-20",
        sector="Technology",
    )
    assert set(view.keys()) == {"Technology"}


def test_excludes_review_and_outcome_rows(portfolio_db_session: Session) -> None:
    """Test 8: portfolio view shows only record_type='analysis' rows."""
    _insert(
        portfolio_db_session,
        ticker="AAPL",
        sector="Technology",
        confidence=80,
        as_of="2026-04-20",
        record_type="analysis",
    )
    _insert(
        portfolio_db_session,
        ticker="AAPL",
        sector="Technology",
        confidence=99,
        as_of="2026-04-20",
        record_type="review",
    )
    _insert(
        portfolio_db_session,
        ticker="AAPL",
        sector="Technology",
        confidence=99,
        as_of="2026-04-20",
        record_type="outcome",
    )
    portfolio_db_session.commit()

    view = query_portfolio_view(portfolio_db_session, as_of_date="2026-04-20")
    aapl_entries = [e for e in view["Technology"] if e["ticker"] == "AAPL"]
    assert len(aapl_entries) == 1
    # Confirm conviction came from analysis row (80), NOT review/outcome (99)
    assert aapl_entries[0]["conviction"] == 80


def test_limit_per_sector_caps(portfolio_db_session: Session) -> None:
    """Test 9: limit_per_sector caps the number of rows returned."""
    for i in range(60):
        _insert(
            portfolio_db_session,
            ticker=f"T{i:03d}",
            sector="Technology",
            confidence=50,
            as_of="2026-04-20",
        )
    portfolio_db_session.commit()

    view = query_portfolio_view(
        portfolio_db_session,
        as_of_date="2026-04-20",
        limit_per_sector=50,
    )
    assert len(view["Technology"]) == 50


def test_entry_shape(portfolio_db_session: Session) -> None:
    """Test 10: each entry has the contract's exact key set + values."""
    _insert(
        portfolio_db_session,
        ticker="AAPL",
        sector="Technology",
        confidence=80,
        as_of="2026-04-20",
    )
    portfolio_db_session.commit()

    view = query_portfolio_view(portfolio_db_session, as_of_date="2026-04-20")
    entry = view["Technology"][0]
    expected_keys = {
        "ticker",
        "sector",
        "conviction",
        "direction",
        "thesis_summary",
        "as_of_date",
        "episodic_id",
        "policy_sha",
    }
    assert set(entry.keys()) == expected_keys
    assert entry["as_of_date"] == "2026-04-20"
    assert entry["policy_sha"] == "a" * 64
    assert entry["thesis_summary"] == "AAPL bull case"
    assert entry["ticker"] == "AAPL"
    assert entry["sector"] == "Technology"
    assert entry["conviction"] == 80
    assert entry["direction"] == "long"
    assert isinstance(entry["episodic_id"], int)


def test_no_lru_cache_decorator() -> None:
    """Test 11: Pitfall C regression -- portfolio_view MUST NOT use a cache."""
    src = Path("src/ai_hedge_fund/output/portfolio_view.py").read_text()
    assert "lru_cache" not in src
    assert "@cache" not in src
