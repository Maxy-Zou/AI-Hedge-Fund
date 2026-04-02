"""Public API return types for the AI Washing Detector.

These frozen dataclasses define the contracts returned by the scoring API.
They are intentionally separate from internal Pydantic models to provide
stable, immutable output types for downstream consumers (portfolio management,
trade execution, dashboards).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class CompanyScore:
    """Immutable composite score result for a single company.

    Attributes:
        ticker: Stock ticker symbol.
        company_name: Full company name.
        scored_at: UTC timestamp when the score was computed.
        composite_score: Weighted average risk score (0-100 integer).
        risk_band: One of "genuine", "mixed", "significant_risk", "strong_short".
        confidence: Sum of original weights for available signals (0.0-1.0).
        signal_breakdown: Per-signal scores {signal_type: score}.
        weights_used: Renormalized weights actually applied {weight_key: weight}.
        signals_available: Signal types that contributed to the composite.
        signals_missing: Signal types that were unavailable.
        run_id: Unique identifier for this scoring run.
        signal_freshness: Maps signal_type to most recent as_of_date for that
            signal. None when not populated by the query layer.
    """

    ticker: str
    company_name: str
    scored_at: datetime
    composite_score: int
    risk_band: str
    confidence: float
    signal_breakdown: dict[str, int]
    weights_used: dict[str, float]
    signals_available: list[str]
    signals_missing: list[str]
    run_id: uuid.UUID
    signal_freshness: dict[str, date] | None = field(default=None)
