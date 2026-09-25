"""Attribution rollup over the P&L series (Phase 11, MTM-03; 11-SPEC s7, D7).

Computed on read, never stored: rows already carry each signal's frozen labels.
Rows are cumulative, so a signal's P&L over ``[start, end]`` is its last total on
or before ``end`` minus its last total before ``start``. That P&L is then assigned
along three dimensions -- analyst (split equally across credited analysts to the
cent), debate winner, conviction bucket -- and each dimension must sum *exactly*
to the total (criterion 11.3). A mismatch raises; it is never logged and returned.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ai_hedge_fund.mtm.attribution import ANALYSTS, split_cents
from ai_hedge_fund.mtm.errors import AttributionInvariantError
from ai_hedge_fund.mtm.policy import UNKNOWN_BUCKET
from ai_hedge_fund.mtm.store import query_pnl_rows

ANALYST_KEYS = (*ANALYSTS, "none_aligned", "unattributed")
DEBATE_KEYS = ("bull", "bear", "draw", "unattributed")


@dataclass(frozen=True)
class RollupRow:
    signal_id: int
    pnl_date: date
    total_pnl_cents: int
    attribution: dict[str, Any]
    mtm_policy_sha: str


class AttributionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: date
    end: date
    total_pnl_cents: int
    by_analyst: dict[str, int]
    by_debate_winner: dict[str, int]
    by_conviction_bucket: dict[str, int]
    signals: int
    mtm_policy_shas: tuple[str, ...]


def _range_pnl(rows: Sequence[RollupRow], start: date, end: date) -> tuple[int, RollupRow] | None:
    """(P&L over the range, latest row <= end) for one signal's rows, or None if none <= end."""
    upto_end = [r for r in rows if r.pnl_date <= end]
    if not upto_end:
        return None
    before = [r for r in rows if r.pnl_date < start]
    latest = max(upto_end, key=lambda r: r.pnl_date)
    baseline = max(before, key=lambda r: r.pnl_date).total_pnl_cents if before else 0
    return latest.total_pnl_cents - baseline, latest


def _assign_analysts(by_analyst: dict[str, int], attribution: dict[str, Any], pnl: int) -> None:
    if attribution.get("attribution_schema") != "v2":
        by_analyst["unattributed"] += pnl
        return
    credited = [a for a in ANALYSTS if a in attribution.get("credited_analysts", [])]
    if not credited:
        by_analyst["none_aligned"] += pnl
        return
    for analyst, cents in zip(credited, split_cents(pnl, len(credited)), strict=True):
        by_analyst[analyst] += cents


def _check_sums(total: int, **dims: dict[str, int]) -> None:
    for name, dim in dims.items():
        if sum(dim.values()) != total:
            raise AttributionInvariantError(f"{name} sums to {sum(dim.values())}, total is {total}")


def rollup_rows(rows: Sequence[RollupRow], start: date, end: date) -> AttributionReport:
    """Pure rollup of cumulative P&L rows over ``[start, end]`` (inclusive)."""
    if start > end:
        raise ValueError(f"start {start.isoformat()} is after end {end.isoformat()}")
    by_signal: dict[int, list[RollupRow]] = {}
    for r in rows:
        by_signal.setdefault(r.signal_id, []).append(r)
    by_analyst = dict.fromkeys(ANALYST_KEYS, 0)
    by_debate = dict.fromkeys(DEBATE_KEYS, 0)
    by_bucket: dict[str, int] = {}
    total = signals = 0
    for signal_rows in by_signal.values():
        found = _range_pnl(signal_rows, start, end)
        if found is None:
            continue
        pnl, latest = found
        signals += 1
        total += pnl
        _assign_analysts(by_analyst, latest.attribution, pnl)
        winner = latest.attribution.get("debate_winner", "unattributed")
        by_debate[winner] = by_debate.get(winner, 0) + pnl
        bucket = latest.attribution.get("conviction_bucket", UNKNOWN_BUCKET)
        by_bucket[bucket] = by_bucket.get(bucket, 0) + pnl
    _check_sums(total, by_analyst=by_analyst, by_debate_winner=by_debate, by_conviction=by_bucket)
    return AttributionReport(
        start=start,
        end=end,
        total_pnl_cents=total,
        by_analyst=by_analyst,
        by_debate_winner=by_debate,
        by_conviction_bucket=dict(sorted(by_bucket.items())),
        signals=signals,
        mtm_policy_shas=tuple(
            sorted({r.mtm_policy_sha for r in rows if start <= r.pnl_date <= end})
        ),
    )


def attribution_rollup(db_session: Session, start: date, end: date) -> AttributionReport:
    """Rollup of ``paper_pnl_daily`` over ``[start, end]``; Phase 13's report calls this."""
    rows = [
        RollupRow(
            signal_id=r.signal_id,
            pnl_date=date.fromisoformat(r.pnl_date),
            total_pnl_cents=r.total_pnl_cents,
            attribution=r.attribution,
            mtm_policy_sha=r.mtm_policy_sha,
        )
        for r in query_pnl_rows(db_session, on_or_before=end)
    ]
    return rollup_rows(rows, start, end)
