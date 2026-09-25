"""Phase 11 T7 -- EOD mark-to-market job (11-SPEC s6, D6, A1).

Fixtures build the ledger through the real stores. Calendar: 2026-09-02 is a
Wednesday; ``NOW`` is Thursday 2026-09-10 evening, so every earlier weekday is a
completed trading day.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of, trading_date
from ai_hedge_fund.db.models import DailyPrice, EpisodicMemory
from ai_hedge_fund.mtm.errors import IncompleteTradingDay
from ai_hedge_fund.mtm.job import JobResult, run_mark_to_market
from ai_hedge_fund.mtm.policy import compute_mtm_policy_sha, load_mtm_policy
from ai_hedge_fund.mtm.records import NewCashEvent
from ai_hedge_fund.mtm.store import insert_cash_event, query_pnl_rows
from ai_hedge_fund.paper.records import NewPaperFill, NewPaperTrade
from ai_hedge_fund.paper.store import insert_paper_fill, insert_paper_trade

POLICY = load_mtm_policy()
SHA = "d" * 64
NOW = datetime(2026, 9, 10, 22, 0, tzinfo=UTC)
V2 = {
    "schema_version": 2,
    "analyst_stances": {"fundamental": "bull", "sentiment": "neutral", "technical": "bull"},
    "debate": {"pre_debate_confidence": 60, "post_debate_confidence": 72, "quality_score": 80},
}
_ids = iter(range(1, 10_000))


# --------------------------------------------------------------------------- fixtures


def analysis(
    s: Session, ticker: str = "AAPL", confidence: int = 80, payload: dict | None = None
) -> int:
    row = EpisodicMemory(
        ticker=ticker,
        sector="Technology",
        record_type="analysis",
        signal_direction="long",
        confidence=confidence,
        policy_sha=SHA,
        as_of_date=normalise_as_of("2026-09-01"),
        payload=payload if payload is not None else V2,
    )
    s.add(row)
    s.commit()
    return row.id


def trade(s: Session, sid: int, ticker: str = "AAPL", side: str = "buy", attempt: int = 1) -> int:
    return insert_paper_trade(
        s,
        NewPaperTrade(
            signal_id=sid,
            attempt_no=attempt,
            ticker=ticker,
            side=side,
            order_type="market",
            quantity=10,
            submit_status="submitted",
            broker_order_id=f"ord-{next(_ids)}",
            risk_status_at_submit="APPROVED",
            policy_sha=SHA,
            review_policy_sha=SHA,
            as_of_date="2026-09-01",
            payload={"schema_version": 1},
        ),
    ).id


def fill(s: Session, tid: int, qty: int, price: int, day: int, hour: int = 14) -> int:
    at = datetime(2026, 9, day, hour, 0, tzinfo=UTC)
    return insert_paper_fill(
        s,
        NewPaperFill(
            trade_id=tid,
            broker_fill_id=f"fill-{next(_ids)}",
            filled_qty=qty,
            fill_price_cents=price,
            filled_at=at,
            as_of_date=trading_date(at),
            payload={},
        ),
    ).id


def price(
    s: Session,
    day: int,
    close: int,
    *,
    ticker: str = "AAPL",
    adj: int | None = None,
    source: str = "yfinance",
    observed: datetime | None = None,
) -> int:
    row = DailyPrice(
        ticker=ticker,
        trade_date=date(2026, 9, day),
        open_cents=close,
        high_cents=close,
        low_cents=close,
        close_cents=close,
        adj_close_cents=adj if adj is not None else close,
        volume=1_000,
        source=source,
        as_of_date=normalise_as_of(date(2026, 9, day)),
        observed_date=observed or datetime(2026, 9, day, 22, 0, tzinfo=UTC),
    )
    s.add(row)
    s.commit()
    return row.id


def cash(s: Session, kind: str, day: int, net: int, ticker: str = "AAPL") -> int:
    rec = insert_cash_event(
        s,
        NewCashEvent(
            broker_activity_id=f"act-{next(_ids)}",
            activity_type=kind,  # type: ignore[arg-type]
            ticker=ticker,
            event_date=date(2026, 9, day),
            net_amount_cents=net,
            payload={},
        ),
    )
    assert rec is not None
    return rec.id


def run(s: Session, day: int, *, now: datetime = NOW, dry_run: bool = False) -> JobResult:
    return run_mark_to_market(s, date(2026, 9, day), POLICY, now=now, dry_run=dry_run)


def held(s: Session, qty: int = 10, px: int = 10_000, ticker: str = "AAPL", **kw: object) -> int:
    sid = analysis(s, ticker=ticker, **kw)  # type: ignore[arg-type]
    fill(s, trade(s, sid, ticker=ticker), qty, px, day=2)
    return sid


@pytest.fixture()
def statements(db_session: Session) -> Iterator[list[str]]:
    seen: list[str] = []
    engine = db_session.get_bind()

    def _record(conn, cursor, statement, params, context, executemany) -> None:  # noqa: ANN001
        seen.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(engine, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", _record)


def _snapshot(s: Session) -> list[tuple]:
    return [tuple(r) for r in s.execute(text("SELECT * FROM paper_pnl_daily ORDER BY id"))]


# --------------------------------------------------------------------------- happy path


def test_marks_an_open_position(db_session: Session) -> None:
    sid = held(db_session)
    price_id = price(db_session, 3, 10_500)
    result = run(db_session, 3)
    assert (result.inserted, result.skipped_existing) == (1, 0)
    [row] = query_pnl_rows(db_session, signal_id=sid)
    assert row.pnl_date == "2026-09-03"
    assert (row.open_qty, row.open_cost_cents, row.mark_close_cents) == (10, 100_000, 10_500)
    assert (row.realized_pnl_cents, row.unrealized_pnl_cents, row.total_pnl_cents) == (
        0,
        5_000,
        5_000,
    )
    assert row.price_source == "yfinance"
    assert row.mtm_policy_sha == compute_mtm_policy_sha(POLICY)
    assert row.attribution == {
        "attribution_schema": "v2",
        "credited_analysts": ["fundamental", "technical"],
        "debate_winner": "bull",
        "conviction_bucket": "high",
    }
    assert row.payload["price_row_id"] == price_id
    assert len(row.payload["fill_ids"]) == 1


def test_v1_analysis_is_unattributed(db_session: Session) -> None:
    sid = held(db_session, payload={"schema_version": 1}, confidence=55)
    price(db_session, 3, 10_000)
    run(db_session, 3)
    [row] = query_pnl_rows(db_session, signal_id=sid)
    assert row.attribution["attribution_schema"] == "unattributed"
    assert row.attribution["conviction_bucket"] == "medium"


def test_mark_uses_close_cents_not_adj_close(db_session: Session) -> None:
    """11-PREMORTEM #13 (A1)."""
    sid = held(db_session)
    price(db_session, 3, close=10_500, adj=9_900)
    run(db_session, 3)
    [row] = query_pnl_rows(db_session, signal_id=sid)
    assert row.mark_close_cents == 10_500 and row.unrealized_pnl_cents == 5_000


# ------------------------------------------------------------------ completed-day guard (D6)


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 9, 3, 19, 0, tzinfo=UTC),  # 15:00 ET on the day
        datetime(2026, 9, 3, 20, 29, tzinfo=UTC),  # 16:29 ET, inside the 30-min buffer
        datetime(2026, 9, 2, 22, 0, tzinfo=UTC),  # the day before
    ],
    ids=["intraday", "inside-buffer", "future-date"],
)
def test_today_before_close_raises_incomplete(db_session: Session, now: datetime) -> None:
    """11-PREMORTEM #1."""
    held(db_session)
    price(db_session, 3, 10_500, observed=datetime(2026, 9, 2, 0, 0, tzinfo=UTC))
    with pytest.raises(IncompleteTradingDay):
        run(db_session, 3, now=now)
    assert query_pnl_rows(db_session) == []


def test_today_after_close_buffer_allowed(db_session: Session) -> None:
    held(db_session)
    price(db_session, 3, 10_500, observed=datetime(2026, 9, 3, 20, 30, tzinfo=UTC))
    result = run(db_session, 3, now=datetime(2026, 9, 3, 20, 30, tzinfo=UTC))  # 16:30 ET
    assert result.inserted == 1


@pytest.mark.parametrize("day", [5, 6], ids=["saturday", "sunday"])
def test_weekend_date_raises(db_session: Session, day: int) -> None:
    with pytest.raises(IncompleteTradingDay, match="weekday"):
        run(db_session, day)


# --------------------------------------------------------------------------- prices


def test_missing_exact_date_price_skips_not_stale(db_session: Session) -> None:
    """11-PREMORTEM #2: yesterday's close is never frozen as today's mark."""
    sid = held(db_session)
    price(db_session, 2, 10_000)
    result = run(db_session, 3)
    assert result.skipped_no_price == (sid,) and result.inserted == 0
    assert query_pnl_rows(db_session) == []


def test_price_observed_after_now_ignored(db_session: Session) -> None:
    """11-PREMORTEM #12."""
    sid = held(db_session)
    price(db_session, 3, 10_500, observed=datetime(2026, 9, 11, 0, 0, tzinfo=UTC))
    assert run(db_session, 3).skipped_no_price == (sid,)


def test_same_day_sources_resolve_to_latest_observed(db_session: Session) -> None:
    sid = held(db_session)
    price(db_session, 3, 10_400, source="yfinance", observed=datetime(2026, 9, 3, 21, tzinfo=UTC))
    price(db_session, 3, 10_600, source="tiingo", observed=datetime(2026, 9, 3, 23, tzinfo=UTC))
    run(db_session, 3)
    [row] = query_pnl_rows(db_session, signal_id=sid)
    assert (row.mark_close_cents, row.price_source) == (10_600, "tiingo")


def test_one_ticker_missing_does_not_block_others(db_session: Session) -> None:
    a = held(db_session, ticker="AAPL")
    m = held(db_session, ticker="MSFT")
    price(db_session, 3, 10_500, ticker="MSFT")
    result = run(db_session, 3)
    assert result.skipped_no_price == (a,) and result.inserted == 1
    assert [r.signal_id for r in query_pnl_rows(db_session)] == [m]


# --------------------------------------------------------------------------- idempotency (MTM-04)


def test_rerun_issues_no_update(db_session: Session, statements: list[str]) -> None:
    """11-PREMORTEM #3 / criterion 11.2."""
    held(db_session)
    price(db_session, 3, 10_500)
    run(db_session, 3)
    statements.clear()
    again = run(db_session, 3)
    assert (again.inserted, again.skipped_existing) == (0, 1)
    assert not {"UPDATE", "DELETE"} & set(statements)


def test_rerun_after_new_price_source_inserts_nothing(db_session: Session) -> None:
    """11-PREMORTEM #4."""
    sid = held(db_session)
    price(db_session, 3, 10_500)
    run(db_session, 3)
    price(db_session, 3, 11_000, source="tiingo", observed=datetime(2026, 9, 4, 1, tzinfo=UTC))
    assert run(db_session, 3).inserted == 0
    [row] = query_pnl_rows(db_session, signal_id=sid)
    assert row.mark_close_cents == 10_500


def test_prior_rows_byte_identical(db_session: Session) -> None:
    """11-PREMORTEM #5 / criterion 11.4: every column, JSON text included."""
    held(db_session)
    price(db_session, 3, 10_500)
    cash(db_session, "DIV", 3, 240)
    run(db_session, 3)
    before = _snapshot(db_session)
    price(db_session, 3, 11_111, source="tiingo", observed=datetime(2026, 9, 4, 1, tzinfo=UTC))
    held(db_session, ticker="AAPL")  # a new signal on the same ticker
    run(db_session, 3)
    assert _snapshot(db_session)[: len(before)] == before


def test_dry_run_writes_nothing(db_session: Session) -> None:
    held(db_session)
    price(db_session, 3, 10_500)
    result = run(db_session, 3, dry_run=True)
    assert result.inserted == 0 and len(result.rows) == 1
    assert query_pnl_rows(db_session) == []


# --------------------------------------------------------------------------- temporal


def test_backfill_ignores_later_fills(db_session: Session) -> None:
    """11-PREMORTEM #9."""
    late = analysis(db_session)
    fill(db_session, trade(db_session, late), 5, 10_000, day=4)
    mixed = held(db_session, qty=10)
    fill(db_session, trade(db_session, mixed, attempt=2), 7, 10_000, day=4)
    price(db_session, 3, 10_500)
    result = run(db_session, 3)
    assert result.inserted == 1
    [row] = query_pnl_rows(db_session)
    assert (row.signal_id, row.open_qty) == (mixed, 10)


def test_backfill_ignores_later_dividends(db_session: Session) -> None:
    """11-PREMORTEM #10."""
    sid = held(db_session)
    price(db_session, 3, 10_000)
    cash(db_session, "DIV", 8, 500)
    run(db_session, 3)
    [row] = query_pnl_rows(db_session, signal_id=sid)
    assert row.realized_pnl_cents == 0


# ------------------------------------------------------------ dividends, actions, oversell


def test_dividend_split_pro_rata_across_signals(db_session: Session) -> None:
    """11-PREMORTEM #15: sum of credits == what the broker paid, exactly."""
    a = held(db_session, qty=30)
    b = held(db_session, qty=10)
    cash(db_session, "DIV", 3, 101)
    price(db_session, 3, 10_000)
    run(db_session, 3)
    credits = {r.signal_id: r.realized_pnl_cents for r in query_pnl_rows(db_session)}
    assert credits == {a: 76, b: 25}


def test_dividend_before_a_signal_held_goes_to_holders_only(db_session: Session) -> None:
    early = held(db_session, qty=10)
    later = analysis(db_session)
    fill(db_session, trade(db_session, later), 10, 10_000, day=4)
    cash(db_session, "DIV", 3, 200)
    price(db_session, 4, 10_000)
    run(db_session, 4)
    credits = {r.signal_id: r.realized_pnl_cents for r in query_pnl_rows(db_session)}
    assert credits == {early: 200, later: 0}


def test_split_after_first_fill_skips_signal(db_session: Session) -> None:
    """11-PREMORTEM #14: a raw-close mark across an unapplied split would be fiction."""
    sid = held(db_session)
    cash(db_session, "SPLIT", 3, 0)
    price(db_session, 3, 5_000)
    result = run(db_session, 3)
    assert result.skipped_corporate_action == (sid,) and result.inserted == 0


def test_split_before_first_fill_does_not_skip(db_session: Session) -> None:
    cash(db_session, "SPLIT", 1, 0)
    held(db_session)
    price(db_session, 3, 10_000)
    assert run(db_session, 3).inserted == 1


def test_oversold_signal_skipped_others_marked(db_session: Session) -> None:
    """11-PREMORTEM #17."""
    bad = analysis(db_session)
    fill(db_session, trade(db_session, bad), 3, 10_000, day=2)
    fill(db_session, trade(db_session, bad, side="sell", attempt=2), 5, 10_000, day=3)
    good = held(db_session)
    price(db_session, 3, 10_000)
    result = run(db_session, 3)
    assert result.skipped_oversold == (bad,)
    assert [r.signal_id for r in query_pnl_rows(db_session)] == [good]


# --------------------------------------------------------------------------- review round (T10)


def test_price_observed_before_close_is_not_a_close(db_session: Session) -> None:
    """Review H3: an intraday bar cached at 11:00 ET must not be frozen as the day's close."""
    sid = held(db_session)
    price(db_session, 3, 10_100, observed=datetime(2026, 9, 3, 15, 0, tzinfo=UTC))
    result = run(db_session, 3)
    assert result.skipped_no_price == (sid,) and result.inserted == 0


def test_pre_split_date_marked_with_post_split_price_row_is_skipped(db_session: Session) -> None:
    """Review H4: yfinance Close is split-adjusted as of download; a D3 row fetched after a
    D9 split carries post-split prices for pre-split shares."""
    sid = held(db_session)
    cash(db_session, "SPLIT", 9, 0)
    price(db_session, 3, 5_000, observed=datetime(2026, 9, 9, 22, 0, tzinfo=UTC))
    result = run(db_session, 3)
    assert result.skipped_corporate_action == (sid,) and result.inserted == 0


def test_price_fetched_before_a_later_split_is_used(db_session: Session) -> None:
    held(db_session)
    cash(db_session, "SPLIT", 9, 0)
    price(db_session, 3, 10_000)  # observed D3 evening, before the split
    assert run(db_session, 3).inserted == 1


def test_zero_close_is_no_price_not_a_crash(db_session: Session) -> None:
    """Review LOW: one corrupt price row must not abort every other ticker's mark."""
    a = held(db_session, ticker="AAPL")
    held(db_session, ticker="MSFT")
    price(db_session, 3, 0, ticker="AAPL")
    price(db_session, 3, 10_000, ticker="MSFT")
    result = run(db_session, 3)
    assert result.skipped_no_price == (a,) and result.inserted == 1


@pytest.mark.parametrize(
    ("observed", "marked"),
    [
        (datetime(2026, 9, 3, 20, 29, tzinfo=UTC), False),
        (datetime(2026, 9, 3, 20, 30, tzinfo=UTC), True),
    ],
    ids=["16:29-ET", "16:30-ET"],
)
def test_close_observation_boundary_is_exact(
    db_session: Session, observed: datetime, marked: bool
) -> None:
    held(db_session)
    price(db_session, 3, 10_000, observed=observed)
    assert (run(db_session, 3).inserted == 1) is marked
