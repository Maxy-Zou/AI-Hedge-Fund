"""Frozen Pydantic models for the mark-to-market tables (11-SPEC s3).

``NewPnlRow`` / ``NewCashEvent`` validate at the boundary before anything
touches the session; ``PnlRowRecord`` / ``CashEventRecord`` are immutable read
views with dates as ISO-8601 strings (the ``paper/records.py`` convention).
Money is ``strict`` int: a float never coerces to cents.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_hedge_fund.paper.records import _SECRET_LIKE

CashActivityType = Literal[
    "DIV", "DIVCGL", "DIVCGS", "DIVNRA", "DIVROC", "DIVTXEX", "DIVWH", "SPLIT", "SPIN", "MA", "NC"
]
NON_CASH_ACTIVITY_TYPES = frozenset({"SPLIT", "SPIN", "MA", "NC"})


def _reject_secret_keys(payload: dict[str, Any]) -> None:
    bad = [k for k in payload if _SECRET_LIKE.search(k)]
    if bad:
        raise ValueError(f"payload top-level keys look like secrets: {bad}")


class NewPnlRow(BaseModel):
    """Validated input for :func:`ai_hedge_fund.mtm.store.insert_pnl_rows`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: int = Field(ge=1, strict=True)
    pnl_date: date
    ticker: str = Field(min_length=1, max_length=10)
    open_qty: int = Field(ge=0, strict=True)
    open_cost_cents: int = Field(ge=0, strict=True)
    mark_close_cents: int = Field(gt=0, strict=True)
    price_source: str = Field(min_length=1, max_length=20)
    realized_pnl_cents: int = Field(strict=True)
    unrealized_pnl_cents: int = Field(strict=True)
    total_pnl_cents: int = Field(strict=True)
    attribution: dict[str, Any]
    mtm_policy_sha: str = Field(min_length=64, max_length=64)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def _invariants(self) -> NewPnlRow:
        if self.total_pnl_cents != self.realized_pnl_cents + self.unrealized_pnl_cents:
            raise ValueError("total_pnl_cents must equal realized + unrealized")
        _reject_secret_keys(self.payload)
        return self


class NewCashEvent(BaseModel):
    """Validated input for :func:`ai_hedge_fund.mtm.store.insert_cash_event`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    broker_activity_id: str = Field(min_length=1, max_length=64)
    activity_type: CashActivityType
    ticker: str = Field(min_length=1, max_length=10)
    event_date: date
    net_amount_cents: int = Field(strict=True)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def _invariants(self) -> NewCashEvent:
        if self.activity_type in NON_CASH_ACTIVITY_TYPES and self.net_amount_cents != 0:
            raise ValueError(
                f"{self.activity_type} is a non-cash action; net_amount_cents must be 0"
            )
        _reject_secret_keys(self.payload)
        return self


class PnlRowRecord(BaseModel):
    """Immutable view of one ``paper_pnl_daily`` row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    signal_id: int
    pnl_date: str
    ticker: str
    open_qty: int
    open_cost_cents: int
    mark_close_cents: int
    price_source: str
    realized_pnl_cents: int
    unrealized_pnl_cents: int
    total_pnl_cents: int
    attribution: dict[str, Any]
    mtm_policy_sha: str
    payload: dict[str, Any]
    as_of_date: str
    observed_date: str


class CashEventRecord(BaseModel):
    """Immutable view of one ``paper_cash_events`` row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    broker_activity_id: str
    activity_type: str
    ticker: str
    event_date: str
    net_amount_cents: int
    payload: dict[str, Any]
    as_of_date: str
    observed_date: str
