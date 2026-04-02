"""Unit tests for earnings vagueness scoring config and earningscall_api_key."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_washer.config import AppSettings, EarningsVaguenessScoringConfig, ScoringConfig


class TestEarningsVaguenessScoringConfig:
    """Tests for EarningsVaguenessScoringConfig Pydantic model."""

    def test_default_values(self) -> None:
        """EarningsVaguenessScoringConfig has correct defaults."""
        cfg = EarningsVaguenessScoringConfig()
        assert cfg.buzzword_weight == 0.70
        assert cfg.sentiment_weight == 0.30
        assert cfg.sigmoid_midpoint == 1.0
        assert cfg.sigmoid_steepness == 2.0

    def test_rejects_weights_not_summing_to_one(self) -> None:
        """EarningsVaguenessScoringConfig rejects buzzword_weight + sentiment_weight != 1.0."""
        with pytest.raises(ValidationError, match="must sum to 1.0"):
            EarningsVaguenessScoringConfig(
                buzzword_weight=0.50,
                sentiment_weight=0.30,
            )

    def test_accepts_weights_summing_to_one(self) -> None:
        """EarningsVaguenessScoringConfig accepts valid weight combos."""
        cfg = EarningsVaguenessScoringConfig(
            buzzword_weight=0.60,
            sentiment_weight=0.40,
        )
        assert cfg.buzzword_weight == 0.60
        assert cfg.sentiment_weight == 0.40


class TestScoringConfigEarnings:
    """Tests for ScoringConfig earnings_vagueness field."""

    def test_scoring_config_has_earnings_vagueness(self) -> None:
        """ScoringConfig().earnings_vagueness returns valid EarningsVaguenessScoringConfig."""
        cfg = ScoringConfig()
        assert isinstance(cfg.earnings_vagueness, EarningsVaguenessScoringConfig)
        assert cfg.earnings_vagueness.buzzword_weight == 0.70


class TestAppSettingsEarningscallKey:
    """Tests for earningscall_api_key on AppSettings."""

    def test_earningscall_api_key_default_empty(self) -> None:
        """AppSettings accepts earningscall_api_key='' (optional, default empty)."""
        settings = AppSettings(
            database_url="postgresql://test:test@localhost/test",
            edgar_identity="test test@example.com",
        )
        assert settings.earningscall_api_key == ""

    def test_earningscall_api_key_custom(self) -> None:
        """AppSettings accepts a provided earningscall_api_key."""
        settings = AppSettings(
            database_url="postgresql://test:test@localhost/test",
            edgar_identity="test test@example.com",
            earningscall_api_key="my-api-key-123",
        )
        assert settings.earningscall_api_key == "my-api-key-123"
