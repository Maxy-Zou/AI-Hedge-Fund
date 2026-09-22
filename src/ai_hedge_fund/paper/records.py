"""Frozen Pydantic models for the paper-trading ledger.

``NewPaperTrade`` / ``NewPaperFill`` validate inputs at the boundary
before anything touches the session; ``PaperTradeRecord`` /
``PaperFillRecord`` are immutable read views (dates as ISO-8601 strings,
matching :class:`ai_hedge_fund.memory.episodic.EpisodicHit`).

Money and quantity fields are ``strict`` ints: a float never coerces, so
``123.45`` cannot silently become ``123`` cents (09-PREMORTEM.md #18).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SECRET_LIKE = re.compile(r"secret|api_key|token|password", re.IGNORECASE)

Side = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
SubmitStatus = Literal["submitted", "rejected", "refused_veto"]


class NewPaperTrade(BaseModel):
    """Validated input for :func:`ai_hedge_fund.paper.store.insert_paper_trade`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: int = Field(ge=1, strict=True)
    attempt_no: int = Field(default=1, ge=1, strict=True)
    ticker: str = Field(min_length=1, max_length=10)
    side: Side
    order_type: OrderType
    quantity: int = Field(gt=0, strict=True)
    limit_price_cents: int | None = Field(default=None, gt=0, strict=True)
    submit_status: SubmitStatus
    broker_order_id: str | None = Field(default=None, min_length=1, max_length=64)
    risk_status_at_submit: str = Field(min_length=1, max_length=10)
    policy_sha: str = Field(min_length=64, max_length=64)
    review_policy_sha: str = Field(min_length=64, max_length=64)
    as_of_date: str | date | datetime
    payload: dict[str, Any]

    @model_validator(mode="after")
    def _structural_invariants(self) -> NewPaperTrade:
        if (self.order_type == "limit") != (self.limit_price_cents is not None):
            raise ValueError("limit_price_cents must be set iff order_type == 'limit'")
        if (self.submit_status == "submitted") != (self.broker_order_id is not None):
            raise ValueError("broker_order_id must be set iff submit_status == 'submitted'")
        bad = [k for k in self.payload if _SECRET_LIKE.search(k)]
        if bad:
            raise ValueError(f"payload top-level keys look like secrets: {bad}")
        return self


class NewPaperFill(BaseModel):
    """Validated input for :func:`ai_hedge_fund.paper.store.insert_paper_fill`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trade_id: int = Field(ge=1, strict=True)
    broker_fill_id: str = Field(min_length=1, max_length=64)
    filled_qty: int = Field(gt=0, strict=True)
    fill_price_cents: int = Field(gt=0, strict=True)
    filled_at: datetime
    as_of_date: str | date | datetime
    payload: dict[str, Any]


class PaperTradeRecord(BaseModel):
    """Immutable view of one ``paper_trades`` row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    signal_id: int
    attempt_no: int
    ticker: str
    side: Side
    order_type: OrderType
    quantity: int
    limit_price_cents: int | None
    submit_status: SubmitStatus
    broker_order_id: str | None
    risk_status_at_submit: str
    policy_sha: str
    review_policy_sha: str
    as_of_date: str
    observed_date: str
    payload: dict[str, Any]


class PaperFillRecord(BaseModel):
    """Immutable view of one ``paper_fills`` row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    trade_id: int
    broker_fill_id: str
    filled_qty: int
    fill_price_cents: int
    filled_at: str
    as_of_date: str
    observed_date: str
    payload: dict[str, Any]
