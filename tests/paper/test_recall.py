"""Phase 9 -- temporal recall over the paper ledger (PT-05, ROADMAP 9.5).

Every query filters ``as_of_date <= target``. The seeded ledger carries a
FUTUREX trade and fill dated 2099-01-01; if either ever appears in a query
for an earlier target, the temporal guarantee is broken.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import PaperTrade
from ai_hedge_fund.paper import PaperFillRecord, PaperTradeRecord
from ai_hedge_fund.paper.recall import query_paper_fills, query_paper_trades


def _trade_id(db_session: Session, broker_order_id: str) -> int:
    return db_session.query(PaperTrade).filter_by(broker_order_id=broker_order_id).one().id


# --------------------------------------------------------------------------- PT-05


def test_recall_excludes_future_trades(db_session: Session, seeded_ledger: tuple[int, int]) -> None:
    """FUTUREX trade @ 2099-01-01 MUST NOT leak into a 2030 query."""
    assert query_paper_trades(db_session, as_of_date="2030-01-01", ticker="FUTUREX") == []


def test_recall_excludes_future_fills(db_session: Session, seeded_ledger: tuple[int, int]) -> None:
    """09-PREMORTEM #7: fills are filtered too, not just trades."""
    fills = query_paper_fills(db_session, as_of_date="2030-01-01")
    assert fills, "expected the four 2026 fills"
    assert not any(f.broker_fill_id == "fill-fx-1" for f in fills)
    assert all(f.as_of_date <= "2030-01-01T00:00:00+00:00" for f in fills)


def test_future_rows_visible_once_target_reaches_them(
    db_session: Session, seeded_ledger: tuple[int, int]
) -> None:
    """Sanity: the seed really is there; the filter is what hides it."""
    hits = query_paper_trades(db_session, as_of_date="2099-12-31", ticker="FUTUREX")
    assert [h.broker_order_id for h in hits] == ["ord-futurex"]


def test_boundary_row_at_target_is_included(
    db_session: Session, seeded_ledger: tuple[int, int]
) -> None:
    """09-PREMORTEM #6: ``<=`` not ``<`` -- same-day trades must be visible."""
    on_day = query_paper_trades(db_session, as_of_date="2026-04-01", ticker="AAPL")
    assert [h.broker_order_id for h in on_day] == ["ord-aapl-1"]
    day_before = query_paper_trades(db_session, as_of_date="2026-03-31", ticker="AAPL")
    assert day_before == []


# --------------------------------------------------------------------------- shape / ordering


def test_recall_by_ticker_orders_newest_first(
    db_session: Session, seeded_ledger: tuple[int, int]
) -> None:
    hits = query_paper_trades(db_session, as_of_date="2026-04-30", ticker="AAPL")
    assert [h.broker_order_id for h in hits] == ["ord-aapl-2", "ord-aapl-1"]
    assert all(isinstance(h, PaperTradeRecord) for h in hits)


def test_recall_by_signal_id_respects_temporal_filter_across_attempts(
    db_session: Session, seeded_ledger: tuple[int, int]
) -> None:
    """MSFT: attempt 1 rejected on 04-05, attempt 2 submitted on 04-06."""
    sid = db_session.query(PaperTrade).filter_by(ticker="MSFT").first().signal_id
    both = query_paper_trades(db_session, as_of_date="2026-04-06", signal_id=sid)
    assert [h.attempt_no for h in both] == [2, 1]
    only_first = query_paper_trades(db_session, as_of_date="2026-04-05", signal_id=sid)
    assert [h.attempt_no for h in only_first] == [1]
    assert only_first[0].submit_status == "rejected"


def test_recall_returns_refused_orders_too(
    db_session: Session, seeded_ledger: tuple[int, int]
) -> None:
    """The ledger records refusals; recall does not filter by submit_status."""
    hits = query_paper_trades(db_session, as_of_date="2026-04-30", ticker="NVDA")
    assert len(hits) == 1 and hits[0].submit_status == "refused_veto"


def test_ticker_and_signal_id_narrow_together(
    db_session: Session, seeded_ledger: tuple[int, int]
) -> None:
    sid = db_session.query(PaperTrade).filter_by(ticker="MSFT").first().signal_id
    assert (
        query_paper_trades(db_session, as_of_date="2026-04-30", ticker="AAPL", signal_id=sid) == []
    )


def test_recall_limit(db_session: Session, seeded_ledger: tuple[int, int]) -> None:
    hits = query_paper_trades(db_session, as_of_date="2026-04-30", ticker="AAPL", limit=1)
    assert [h.broker_order_id for h in hits] == ["ord-aapl-2"]


def test_recall_requires_ticker_or_signal_id(db_session: Session) -> None:
    with pytest.raises(ValueError, match="ticker or signal_id"):
        query_paper_trades(db_session, as_of_date="2026-04-30")


def test_naive_and_aware_inputs_equivalent(
    db_session: Session, seeded_ledger: tuple[int, int]
) -> None:
    """09-PREMORTEM #8: every representation of one instant yields identical results."""
    forms = [
        "2026-04-10",
        date(2026, 4, 10),
        datetime(2026, 4, 10),
        datetime(2026, 4, 10, tzinfo=UTC),
        "2026-04-10T00:00:00+00:00",
    ]
    results = [
        [h.id for h in query_paper_trades(db_session, as_of_date=f, ticker="AAPL")] for f in forms
    ]
    assert all(r == results[0] for r in results) and len(results[0]) == 2


# --------------------------------------------------------------------------- fills


def test_fills_by_trade_id(db_session: Session, seeded_ledger: tuple[int, int]) -> None:
    tid = _trade_id(db_session, "ord-aapl-1")
    fills = query_paper_fills(db_session, as_of_date="2026-04-30", trade_id=tid)
    assert sorted(f.filled_qty for f in fills) == [4, 6]
    assert all(isinstance(f, PaperFillRecord) and f.trade_id == tid for f in fills)


def test_fills_limit_and_ordering(db_session: Session, seeded_ledger: tuple[int, int]) -> None:
    fills = query_paper_fills(db_session, as_of_date="2026-04-30", limit=2)
    assert len(fills) == 2
    assert fills[0].as_of_date >= fills[1].as_of_date
