"""Phase 11 T8 -- attribution rollup (11-SPEC s7, D7, criterion 11.3)."""

from __future__ import annotations

import random
from datetime import date

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.mtm import rollup as rollup_mod
from ai_hedge_fund.mtm.errors import AttributionInvariantError
from ai_hedge_fund.mtm.rollup import RollupRow, attribution_rollup, rollup_rows
from tests.mtm.test_job import held, price, run

V2_ATTR = {
    "attribution_schema": "v2",
    "credited_analysts": ["fundamental", "technical"],
    "debate_winner": "bull",
    "conviction_bucket": "high",
}
NONE_ALIGNED = {**V2_ATTR, "credited_analysts": [], "debate_winner": "draw"}
UNATTRIBUTED = {
    "attribution_schema": "unattributed",
    "credited_analysts": [],
    "debate_winner": "unattributed",
    "conviction_bucket": "medium",
}


def row(sid: int, day: int, total: int, attr: dict = V2_ATTR, sha: str = "a" * 64) -> RollupRow:
    return RollupRow(
        signal_id=sid,
        pnl_date=date(2026, 9, day),
        total_pnl_cents=total,
        attribution=attr,
        mtm_policy_sha=sha,
    )


def _sums_hold(report) -> None:  # noqa: ANN001
    for dim in (report.by_analyst, report.by_debate_winner, report.by_conviction_bucket):
        assert sum(dim.values()) == report.total_pnl_cents


def test_single_signal_split_across_credited_analysts() -> None:
    r = rollup_rows([row(1, 3, 101)], date(2026, 9, 1), date(2026, 9, 30))
    assert r.total_pnl_cents == 101
    assert r.by_analyst["fundamental"] == 51 and r.by_analyst["technical"] == 50
    assert r.by_analyst["sentiment"] == 0
    assert r.by_debate_winner["bull"] == 101
    assert r.by_conviction_bucket == {"high": 101}
    assert r.signals == 1
    _sums_hold(r)


def test_range_pnl_is_end_minus_start_baseline() -> None:
    """Rows are cumulative: P&L over [start, end] = last total <= end - last total < start."""
    rows = [row(1, 2, 100), row(1, 3, 150), row(1, 4, 120)]
    assert rollup_rows(rows, date(2026, 9, 3), date(2026, 9, 4)).total_pnl_cents == 20
    assert rollup_rows(rows, date(2026, 9, 2), date(2026, 9, 2)).total_pnl_cents == 100
    assert rollup_rows(rows, date(2026, 9, 7), date(2026, 9, 9)).total_pnl_cents == 0
    assert rollup_rows(rows, date(2026, 9, 1), date(2026, 9, 1)).signals == 0


def test_unattributed_separate_from_none_aligned() -> None:
    """11-PREMORTEM #22."""
    r = rollup_rows(
        [row(1, 3, 40, NONE_ALIGNED), row(2, 3, -15, UNATTRIBUTED)],
        date(2026, 9, 1),
        date(2026, 9, 30),
    )
    assert r.by_analyst["none_aligned"] == 40
    assert r.by_analyst["unattributed"] == -15
    assert r.by_debate_winner == {"bull": 0, "bear": 0, "draw": 40, "unattributed": -15}
    assert r.by_conviction_bucket == {"high": 40, "medium": -15}
    _sums_hold(r)


def test_each_dimension_sums_to_total() -> None:
    """11-PREMORTEM #21 / criterion 11.3: exact, not 'within tolerance', over random books."""
    rng = random.Random(11)
    analysts = ["fundamental", "sentiment", "technical"]
    for _ in range(500):
        rows = []
        for sid in range(1, rng.randint(1, 8)):
            credited = sorted(rng.sample(analysts, rng.randint(0, 3)), key=analysts.index)
            attr = {
                "attribution_schema": rng.choice(["v2", "v2", "unattributed"]),
                "credited_analysts": credited,
                "debate_winner": rng.choice(["bull", "bear", "draw", "unattributed"]),
                "conviction_bucket": rng.choice(["low", "medium", "high", "unknown"]),
            }
            for day in sorted(rng.sample(range(1, 29), rng.randint(1, 4))):
                rows.append(
                    row(sid, day, rng.choice([1, 2, -1, rng.randint(-(10**7), 10**7)]), attr)
                )
        start = date(2026, 9, rng.randint(1, 20))
        _sums_hold(rollup_rows(rows, start, date(2026, 9, rng.randint(start.day, 28))))


def test_invariant_violation_raises_not_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rollup_mod, "split_cents", lambda total, parts: (total // parts,) * parts)
    with pytest.raises(AttributionInvariantError, match="by_analyst"):
        rollup_rows([row(1, 3, 101)], date(2026, 9, 1), date(2026, 9, 30))


def test_policy_shas_reported_when_rules_changed_mid_range() -> None:
    rows = [row(1, 2, 10, sha="a" * 64), row(1, 3, 20, sha="b" * 64)]
    r = rollup_rows(rows, date(2026, 9, 1), date(2026, 9, 30))
    assert r.mtm_policy_shas == ("a" * 64, "b" * 64)


def test_start_after_end_rejected() -> None:
    with pytest.raises(ValueError, match="start"):
        rollup_rows([], date(2026, 9, 5), date(2026, 9, 4))


def test_db_rollup_over_job_output(db_session: Session) -> None:
    held(db_session, qty=10, px=10_000)
    held(db_session, qty=5, px=10_000, payload={"schema_version": 1}, confidence=55)
    price(db_session, 3, 10_300)
    price(db_session, 4, 10_100)
    run(db_session, 3)
    run(db_session, 4)
    report = attribution_rollup(db_session, date(2026, 9, 4), date(2026, 9, 4))
    # Sep 4 alone: (101.00 - 103.00) * 15 shares = -3_000
    assert report.total_pnl_cents == -3_000
    assert report.by_analyst["unattributed"] == -1_000  # signal b, 5 shares
    assert report.by_analyst["fundamental"] + report.by_analyst["technical"] == -2_000
    assert report.signals == 2
    _sums_hold(report)
