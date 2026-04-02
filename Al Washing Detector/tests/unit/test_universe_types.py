"""Tests for universe builder Pydantic type contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestEFTSHit:
    """Tests for EFTSHit -- single EFTS search result."""

    def test_valid_hit(self):
        from ai_washer.universe.types import EFTSHit

        hit = EFTSHit(
            accession_no="0001234567-26-000001",
            form_type="10-K",
            file_date="2026-01-15",
            entity_name="ACME CORPORATION",
            ciks=["0001234567"],
            period_of_report="2025-12-31",
            display_names=["ACME CORPORATION"],
        )
        assert hit.accession_no == "0001234567-26-000001"
        assert hit.form_type == "10-K"
        assert hit.file_date == "2026-01-15"
        assert hit.entity_name == "ACME CORPORATION"
        assert hit.ciks == ["0001234567"]
        assert hit.period_of_report == "2025-12-31"
        assert hit.display_names == ["ACME CORPORATION"]

    def test_optional_fields_default(self):
        from ai_washer.universe.types import EFTSHit

        hit = EFTSHit(
            accession_no="0001234567-26-000002",
            form_type="10-K",
            file_date="2026-03-01",
            entity_name="BETA INC",
            ciks=["0009876543"],
        )
        assert hit.period_of_report is None
        assert hit.display_names == []

    def test_multiple_ciks(self):
        from ai_washer.universe.types import EFTSHit

        hit = EFTSHit(
            accession_no="ACC-001",
            form_type="10-K",
            file_date="2026-02-01",
            entity_name="MERGED CO",
            ciks=["0001111111", "0002222222"],
        )
        assert len(hit.ciks) == 2

    def test_missing_required_field_rejected(self):
        from ai_washer.universe.types import EFTSHit

        with pytest.raises(ValidationError):
            EFTSHit(
                accession_no="ACC-001",
                form_type="10-K",
                # missing file_date, entity_name, ciks
            )


class TestEFTSResponse:
    """Tests for EFTSResponse -- parsed EFTS API response."""

    def test_valid_response(self):
        from ai_washer.universe.types import EFTSHit, EFTSResponse

        hit = EFTSHit(
            accession_no="ACC-001",
            form_type="10-K",
            file_date="2026-01-01",
            entity_name="CORP A",
            ciks=["0001234567"],
        )
        response = EFTSResponse(
            total_value=1,
            total_relation="eq",
            hits=[hit],
        )
        assert response.total_value == 1
        assert response.total_relation == "eq"
        assert len(response.hits) == 1

    def test_is_truncated_false_for_eq(self):
        from ai_washer.universe.types import EFTSResponse

        response = EFTSResponse(
            total_value=50,
            total_relation="eq",
            hits=[],
        )
        assert response.is_truncated is False

    def test_is_truncated_true_for_gte(self):
        """Per plan: EFTSResponse with total_relation='gte' has is_truncated=True."""
        from ai_washer.universe.types import EFTSResponse

        response = EFTSResponse(
            total_value=10000,
            total_relation="gte",
            hits=[],
        )
        assert response.is_truncated is True

    def test_empty_hits_valid(self):
        from ai_washer.universe.types import EFTSResponse

        response = EFTSResponse(
            total_value=0,
            total_relation="eq",
            hits=[],
        )
        assert response.hits == []
        assert response.total_value == 0


class TestMarketCapRange:
    """Tests for MarketCapRange validation."""

    def test_valid_range(self):
        from ai_washer.universe.types import MarketCapRange

        mcr = MarketCapRange(
            min_cents=200_000_000_000,
            max_cents=1_000_000_000_000,
        )
        assert mcr.min_cents == 200_000_000_000
        assert mcr.max_cents == 1_000_000_000_000

    def test_min_must_be_positive(self):
        from ai_washer.universe.types import MarketCapRange

        with pytest.raises(ValidationError, match="min_cents"):
            MarketCapRange(min_cents=0, max_cents=100)

    def test_max_must_be_positive(self):
        from ai_washer.universe.types import MarketCapRange

        with pytest.raises(ValidationError, match="max_cents"):
            MarketCapRange(min_cents=1, max_cents=0)

    def test_min_less_than_max_enforced(self):
        from ai_washer.universe.types import MarketCapRange

        with pytest.raises(ValidationError, match="must be less than"):
            MarketCapRange(min_cents=500, max_cents=500)

    def test_min_greater_than_max_rejected(self):
        from ai_washer.universe.types import MarketCapRange

        with pytest.raises(ValidationError, match="must be less than"):
            MarketCapRange(min_cents=1000, max_cents=500)


class TestUniverseSettings:
    """Tests for UniverseSettings configuration model."""

    def test_default_values(self):
        from ai_washer.config import UniverseSettings

        settings = UniverseSettings()
        assert settings.efts_page_size == 50
        assert settings.market_cap_min_cents == 150_000_000_000  # $1.5B
        assert settings.market_cap_max_cents == 900_000_000_000  # $9B
        assert settings.ai_keywords == ["artificial intelligence", "machine learning"]
        assert settings.fuzzy_match_threshold == 85
        assert settings.refresh_cadence_days == 30

    def test_widened_market_cap_thresholds(self):
        """Per Pitfall 2: thresholds use widened EntityPublicFloat proxy values.

        $1.5B min (wider than $2B target) and $9B max (wider than $10B target)
        to account for the proxy approximation.
        """
        from ai_washer.config import UniverseSettings

        settings = UniverseSettings()
        # $1.5B is less than $2B target to catch border cases
        assert settings.market_cap_min_cents < 200_000_000_000
        # $9B is less than $10B target to exclude clear large-caps
        assert settings.market_cap_max_cents < 1_000_000_000_000

    def test_efts_page_size_bounds(self):
        from ai_washer.config import UniverseSettings

        with pytest.raises(ValidationError, match="efts_page_size"):
            UniverseSettings(efts_page_size=5)

        with pytest.raises(ValidationError, match="efts_page_size"):
            UniverseSettings(efts_page_size=150)

    def test_fuzzy_match_threshold_bounds(self):
        from ai_washer.config import UniverseSettings

        with pytest.raises(ValidationError, match="fuzzy_match_threshold"):
            UniverseSettings(fuzzy_match_threshold=49)

        with pytest.raises(ValidationError, match="fuzzy_match_threshold"):
            UniverseSettings(fuzzy_match_threshold=101)

    def test_refresh_cadence_minimum(self):
        from ai_washer.config import UniverseSettings

        with pytest.raises(ValidationError, match="refresh_cadence_days"):
            UniverseSettings(refresh_cadence_days=0)

    def test_custom_keywords(self):
        from ai_washer.config import UniverseSettings

        settings = UniverseSettings(
            ai_keywords=["deep learning", "neural network", "generative AI"],
        )
        assert len(settings.ai_keywords) == 3
        assert "deep learning" in settings.ai_keywords

    def test_custom_page_size(self):
        from ai_washer.config import UniverseSettings

        settings = UniverseSettings(efts_page_size=100)
        assert settings.efts_page_size == 100
