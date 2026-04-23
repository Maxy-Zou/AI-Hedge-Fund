"""Plan 08-04 Task 2: portfolio_view CLI tests.

Exercises the CLI surface of the SIG-02 ranked view:

    * CLI missing --as-of -> SystemExit non-zero.
    * Empty DB -> friendly ``(no signals)`` markdown (no traceback).
    * Markdown default rendering with sector headers + ticker bullets.
    * --json flag -> valid JSON with sector-keyed entries.
    * --sector filter restricts to a single sector.
    * --limit cap (per-sector DoS guard).
    * Rank order preserved in the JSON output.
"""

from __future__ import annotations

import os

# Match the documented Phase-7 workaround: ``ai_hedge_fund.db.models`` is
# transitively imported by ``query_portfolio_view``; set a dummy API key
# before any ``ai_hedge_fund`` import so provider instantiation does not
# fail if a downstream module eagerly loads an agent.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-phase8-portfolio-view-cli")

import json
from datetime import date

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.scripts.portfolio_view import _main, _run


def _seed(
    session: Session,
    *,
    ticker: str,
    confidence: int,
    sector: str = "Technology",
    as_of: str = "2026-04-20",
    signal_direction: str = "long",
) -> int:
    """Seed a single ``record_type='analysis'`` row and return its id."""
    row = EpisodicMemory(
        ticker=ticker,
        sector=sector,
        record_type="analysis",
        signal_direction=signal_direction,
        confidence=confidence,
        outcome_pct=None,
        linked_analysis_id=None,
        policy_sha="a" * 64,
        as_of_date=date.fromisoformat(as_of),
        payload={"thesis": {"bull_case": f"{ticker} bullish rationale"}},
    )
    session.add(row)
    session.flush()
    return row.id


def test_cli_missing_as_of_exits_nonzero() -> None:
    """argparse required=True on --as-of -> SystemExit non-zero."""
    with pytest.raises(SystemExit) as excinfo:
        _main([])
    assert excinfo.value.code is None or excinfo.value.code != 0


def test_empty_db_markdown(portfolio_db_session: Session) -> None:
    """Empty DB -> friendly ``(no signals)`` output, not a traceback."""
    out = _run(
        portfolio_db_session,
        as_of_date="2026-04-20",
        sector=None,
        limit_per_sector=50,
        as_json=False,
    )
    assert "(no signals)" in out


def test_markdown_default(portfolio_db_session: Session) -> None:
    """Default (non-JSON) render has sector headers + ticker bullets."""
    _seed(portfolio_db_session, ticker="AAPL", confidence=80)
    _seed(portfolio_db_session, ticker="MSFT", confidence=60)
    _seed(portfolio_db_session, ticker="PFE", confidence=70, sector="Healthcare")
    portfolio_db_session.commit()

    out = _run(
        portfolio_db_session,
        as_of_date="2026-04-20",
        sector=None,
        limit_per_sector=50,
        as_json=False,
    )
    assert "# Portfolio View" in out
    assert "## Technology" in out
    assert "## Healthcare" in out
    assert "AAPL" in out and "MSFT" in out and "PFE" in out


def test_json_flag(portfolio_db_session: Session) -> None:
    """--json path produces a parseable dict keyed by sector."""
    _seed(portfolio_db_session, ticker="AAPL", confidence=80)
    portfolio_db_session.commit()

    out = _run(
        portfolio_db_session,
        as_of_date="2026-04-20",
        sector=None,
        limit_per_sector=50,
        as_json=True,
    )
    parsed = json.loads(out)
    assert "Technology" in parsed
    assert parsed["Technology"][0]["ticker"] == "AAPL"


def test_sector_filter(portfolio_db_session: Session) -> None:
    """--sector Technology returns exactly the Technology bucket."""
    _seed(portfolio_db_session, ticker="AAPL", confidence=80)
    _seed(portfolio_db_session, ticker="PFE", confidence=70, sector="Healthcare")
    portfolio_db_session.commit()

    out = _run(
        portfolio_db_session,
        as_of_date="2026-04-20",
        sector="Technology",
        limit_per_sector=50,
        as_json=True,
    )
    parsed = json.loads(out)
    assert set(parsed.keys()) == {"Technology"}


def test_limit_cap(portfolio_db_session: Session) -> None:
    """--limit caps the per-sector entry count."""
    for i in range(60):
        _seed(portfolio_db_session, ticker=f"T{i:03d}", confidence=50)
    portfolio_db_session.commit()

    out = _run(
        portfolio_db_session,
        as_of_date="2026-04-20",
        sector=None,
        limit_per_sector=10,
        as_json=True,
    )
    parsed = json.loads(out)
    assert len(parsed["Technology"]) == 10


def test_rank_order_in_json_output(portfolio_db_session: Session) -> None:
    """JSON entries are sorted by conviction DESC within a sector."""
    _seed(portfolio_db_session, ticker="AAA", confidence=30)
    _seed(portfolio_db_session, ticker="BBB", confidence=80)
    _seed(portfolio_db_session, ticker="CCC", confidence=50)
    portfolio_db_session.commit()

    out = _run(
        portfolio_db_session,
        as_of_date="2026-04-20",
        sector=None,
        limit_per_sector=50,
        as_json=True,
    )
    parsed = json.loads(out)
    assert [e["ticker"] for e in parsed["Technology"]] == ["BBB", "CCC", "AAA"]
