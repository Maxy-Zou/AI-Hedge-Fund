"""Phase 11 T5 -- pure P&L core (11-SPEC s5, A1, D5). No I/O, integer cents only."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, date, datetime

import pytest

from ai_hedge_fund.mtm.errors import FutureInputError, OversoldError
from ai_hedge_fund.mtm.pnl import CashIn, FillIn, PositionMark, mark_position

DAY = date(2026, 9, 4)


def _at(day: int, hour: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, 0, tzinfo=UTC)


def buy(fid: int, qty: int, price: int, day: int = 2, hour: int = 14) -> FillIn:
    return FillIn(fill_id=fid, side="buy", qty=qty, price_cents=price, filled_at=_at(day, hour))


def sell(fid: int, qty: int, price: int, day: int = 3, hour: int = 14) -> FillIn:
    return FillIn(fill_id=fid, side="sell", qty=qty, price_cents=price, filled_at=_at(day, hour))


def div(eid: int, cents: int, day: int = 3) -> CashIn:
    return CashIn(event_id=eid, event_date=date(2026, 9, day), amount_cents=cents)


def test_single_buy_unrealized_only() -> None:
    m = mark_position([buy(1, 10, 10_000)], [], close_cents=10_500, pnl_date=DAY)
    assert m == PositionMark(
        open_qty=10,
        open_cost_cents=100_000,
        realized_pnl_cents=0,
        unrealized_pnl_cents=5_000,
        total_pnl_cents=5_000,
        fill_ids=(1,),
        cash_event_ids=(),
    )


def test_loss_is_negative() -> None:
    m = mark_position([buy(1, 3, 10_001)], [], close_cents=9_999, pnl_date=DAY)
    assert m.unrealized_pnl_cents == -6 and m.total_pnl_cents == -6


def test_fifo_partial_sell_across_lots() -> None:
    fills = [buy(1, 5, 10_000, hour=14), buy(2, 5, 11_000, hour=15), sell(3, 7, 12_000)]
    m = mark_position(fills, [], close_cents=12_500, pnl_date=DAY)
    # sell 7: 5 @ 100.00 (+10_000) and 2 @ 110.00 (+2_000)
    assert m.realized_pnl_cents == 12_000
    assert (m.open_qty, m.open_cost_cents) == (3, 33_000)
    assert m.unrealized_pnl_cents == 3 * 12_500 - 33_000
    assert m.total_pnl_cents == m.realized_pnl_cents + m.unrealized_pnl_cents


def test_fifo_uses_filled_at_then_id() -> None:
    """11-PREMORTEM #16: ingest order (ids) must not change which lot is sold."""
    later_low_id = buy(1, 5, 11_000, hour=15)
    earlier_high_id = buy(9, 5, 10_000, hour=14)
    m = mark_position(
        [later_low_id, earlier_high_id, sell(3, 5, 12_000)], [], close_cents=12_000, pnl_date=DAY
    )
    assert m.realized_pnl_cents == 5 * (12_000 - 10_000)  # the 14:00 lot went first
    tie_a, tie_b = buy(4, 1, 10_000, hour=14), buy(2, 1, 20_000, hour=14)
    m2 = mark_position([tie_a, tie_b, sell(5, 1, 30_000)], [], close_cents=1, pnl_date=DAY)
    assert m2.realized_pnl_cents == 30_000 - 20_000  # same instant -> lower fill id first


def test_full_close_leaves_zero_open() -> None:
    m = mark_position([buy(1, 4, 10_000), sell(2, 4, 9_000)], [], close_cents=8_000, pnl_date=DAY)
    assert (m.open_qty, m.open_cost_cents, m.unrealized_pnl_cents) == (0, 0, 0)
    assert m.realized_pnl_cents == -4_000


def test_oversell_raises() -> None:
    """11-PREMORTEM #17: a long-only book cannot sell what it doesn't hold."""
    with pytest.raises(OversoldError, match="fill 2"):
        mark_position([buy(1, 3, 10_000), sell(2, 4, 10_000)], [], close_cents=1, pnl_date=DAY)


def test_sell_before_any_buy_raises() -> None:
    with pytest.raises(OversoldError):
        mark_position([sell(1, 1, 10_000, day=2), buy(2, 1, 10_000, day=3)], [], 1, DAY)


def test_dividends_are_realized_income() -> None:
    m = mark_position([buy(1, 10, 10_000)], [div(7, 240)], close_cents=10_000, pnl_date=DAY)
    assert (m.realized_pnl_cents, m.unrealized_pnl_cents, m.total_pnl_cents) == (240, 0, 240)
    assert m.cash_event_ids == (7,)


def test_withholding_reduces_realized() -> None:
    """11-PREMORTEM #20."""
    m = mark_position([buy(1, 10, 10_000)], [div(7, 240), div(8, -36)], 10_000, DAY)
    assert m.realized_pnl_cents == 204


def test_future_fill_raises() -> None:
    """11-PREMORTEM #9: the temporal guard is re-asserted inside the core."""
    with pytest.raises(FutureInputError, match="fill 2"):
        mark_position([buy(1, 1, 100), buy(2, 1, 100, day=5)], [], close_cents=100, pnl_date=DAY)


def test_fill_after_hours_on_pnl_date_counts_by_new_york_date() -> None:
    """23:30Z on Sep 4 is 19:30 ET Sep 4 -> same trading day; 04:30Z Sep 5 is still Sep 4 ET."""
    late = FillIn(1, "buy", 1, 100, datetime(2026, 9, 5, 3, 30, tzinfo=UTC))
    assert mark_position([late], [], close_cents=100, pnl_date=DAY).open_qty == 1
    next_day = FillIn(2, "buy", 1, 100, datetime(2026, 9, 5, 4, 30, tzinfo=UTC))
    with pytest.raises(FutureInputError):
        mark_position([next_day], [], close_cents=100, pnl_date=DAY)


def test_future_dividend_raises() -> None:
    """11-PREMORTEM #10."""
    with pytest.raises(FutureInputError, match="cash event 8"):
        mark_position([buy(1, 1, 100)], [div(8, 5, day=5)], close_cents=100, pnl_date=DAY)


def test_total_is_sum_of_parts_and_all_ints() -> None:
    """11-PREMORTEM #7 and money precision: every field is an int, never a float."""
    m = mark_position(
        [buy(1, 7, 10_333), buy(2, 3, 9_999), sell(3, 4, 10_101)],
        [div(1, 17), div(2, -3)],
        close_cents=10_050,
        pnl_date=DAY,
    )
    assert m.total_pnl_cents == m.realized_pnl_cents + m.unrealized_pnl_cents
    for f in fields(PositionMark):
        value = getattr(m, f.name)
        if isinstance(value, tuple):
            assert all(type(v) is int for v in value)
        else:
            assert type(value) is int, f.name


@pytest.mark.parametrize("close", [0, -1])
def test_non_positive_close_rejected(close: int) -> None:
    with pytest.raises(ValueError, match="close_cents"):
        mark_position([buy(1, 1, 100)], [], close_cents=close, pnl_date=DAY)


def test_inputs_are_not_mutated() -> None:
    fills = [buy(1, 5, 10_000), sell(2, 2, 11_000)]
    snapshot = list(fills)
    mark_position(fills, [], close_cents=10_000, pnl_date=DAY)
    assert fills == snapshot
