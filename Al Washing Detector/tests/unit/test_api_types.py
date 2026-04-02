"""Unit tests for public API return types."""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError, fields
from datetime import datetime

import pytest

from ai_washer.api_types import CompanyScore


class TestCompanyScore:
    """Tests for CompanyScore frozen dataclass."""

    def _make_company_score(self) -> CompanyScore:
        return CompanyScore(
            ticker="ACME",
            company_name="Acme Corp",
            scored_at=datetime(2026, 3, 29, 12, 0, 0),
            composite_score=65,
            risk_band="significant_risk",
            confidence=0.85,
            signal_breakdown={"sec_filing": 70, "patent_gap": 60},
            weights_used={"sec_filing": 0.20, "patent_gap": 0.15},
            signals_available=["sec_filing", "patent_gap"],
            signals_missing=["earnings_vagueness", "job_mismatch", "github_activity", "compute_spending"],
            run_id=uuid.uuid4(),
        )

    def test_company_score_is_frozen(self) -> None:
        cs = self._make_company_score()
        with pytest.raises(FrozenInstanceError):
            cs.ticker = "OTHER"  # type: ignore[misc]

    def test_company_score_has_all_fields(self) -> None:
        field_names = {f.name for f in fields(CompanyScore)}
        expected = {
            "ticker",
            "company_name",
            "scored_at",
            "composite_score",
            "risk_band",
            "confidence",
            "signal_breakdown",
            "weights_used",
            "signals_available",
            "signals_missing",
            "run_id",
            "signal_freshness",
        }
        assert field_names == expected

    def test_signal_freshness_defaults_to_none(self) -> None:
        cs = self._make_company_score()
        assert cs.signal_freshness is None
