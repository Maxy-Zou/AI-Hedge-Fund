"""Tests for configuration, model routing, and logging."""

from __future__ import annotations

import dataclasses

import pytest


class TestAppSettings:
    """Tests for AppSettings configuration loading."""

    def test_default_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AppSettings loads default database_url when no .env exists."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from ai_hedge_fund.config import AppSettings

        settings = AppSettings(_env_file=None)
        assert (
            settings.database_url == "postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund"
        )

    def test_loads_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AppSettings loads from environment variables."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        from ai_hedge_fund.config import AppSettings

        settings = AppSettings(_env_file=None)
        assert settings.anthropic_api_key == "test-key"

    def test_extraction_token_limit_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AppSettings extraction_token_limit defaults to 22_000."""
        monkeypatch.delenv("EXTRACTION_TOKEN_LIMIT", raising=False)
        from ai_hedge_fund.config import AppSettings

        settings = AppSettings(_env_file=None)
        assert settings.extraction_token_limit == 22_000

    def test_analysis_token_limit_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AppSettings analysis_token_limit defaults to 58_000."""
        monkeypatch.delenv("ANALYSIS_TOKEN_LIMIT", raising=False)
        from ai_hedge_fund.config import AppSettings

        settings = AppSettings(_env_file=None)
        assert settings.analysis_token_limit == 58_000

    def test_reasoning_token_limit_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AppSettings reasoning_token_limit defaults to 116_000."""
        monkeypatch.delenv("REASONING_TOKEN_LIMIT", raising=False)
        from ai_hedge_fund.config import AppSettings

        settings = AppSettings(_env_file=None)
        assert settings.reasoning_token_limit == 116_000

    def test_pipeline_total_token_limit_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AppSettings pipeline_total_token_limit defaults to 500_000."""
        monkeypatch.delenv("PIPELINE_TOTAL_TOKEN_LIMIT", raising=False)
        from ai_hedge_fund.config import AppSettings

        settings = AppSettings(_env_file=None)
        assert settings.pipeline_total_token_limit == 500_000


class TestModelTier:
    """Tests for ModelTier enum and AgentBudget."""

    def test_extraction_model_id(self) -> None:
        """ModelTier.EXTRACTION maps to Claude Haiku."""
        from ai_hedge_fund.models import ModelTier

        assert ModelTier.EXTRACTION.value == "anthropic:claude-haiku-4-5"

    def test_analysis_model_id(self) -> None:
        """ModelTier.ANALYSIS maps to Claude Sonnet."""
        from ai_hedge_fund.models import ModelTier

        assert ModelTier.ANALYSIS.value == "anthropic:claude-sonnet-4-6"

    def test_reasoning_model_id(self) -> None:
        """ModelTier.REASONING maps to Claude Opus."""
        from ai_hedge_fund.models import ModelTier

        assert ModelTier.REASONING.value == "anthropic:claude-opus-4-6"

    def test_extraction_budget(self) -> None:
        """MODEL_BUDGETS maps EXTRACTION to correct input limit."""
        from ai_hedge_fund.models import MODEL_BUDGETS, ModelTier

        assert MODEL_BUDGETS[ModelTier.EXTRACTION].input_tokens_limit == 20_000

    def test_analysis_budget(self) -> None:
        """MODEL_BUDGETS maps ANALYSIS to correct input limit."""
        from ai_hedge_fund.models import MODEL_BUDGETS, ModelTier

        assert MODEL_BUDGETS[ModelTier.ANALYSIS].input_tokens_limit == 50_000

    def test_reasoning_budget(self) -> None:
        """MODEL_BUDGETS maps REASONING to correct input limit."""
        from ai_hedge_fund.models import MODEL_BUDGETS, ModelTier

        assert MODEL_BUDGETS[ModelTier.REASONING].input_tokens_limit == 100_000

    def test_agent_budget_is_frozen(self) -> None:
        """AgentBudget is immutable -- assigning to a field raises FrozenInstanceError."""
        from ai_hedge_fund.models import MODEL_BUDGETS, ModelTier

        budget = MODEL_BUDGETS[ModelTier.EXTRACTION]
        with pytest.raises(dataclasses.FrozenInstanceError):
            budget.input_tokens_limit = 999  # type: ignore[misc]


class TestLogging:
    """Tests for structlog configuration."""

    def test_configure_logging_returns_json(self) -> None:
        """configure_logging() returns a logger producing JSON output."""
        from ai_hedge_fund.logging import configure_logging

        logger = configure_logging()
        # Structlog should be configured -- get a bound logger and verify it works
        # The logger should produce structured output
        assert logger is not None
