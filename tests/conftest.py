"""Shared test fixtures for the AI Hedge Fund test suite."""

from __future__ import annotations

import pytest

from ai_hedge_fund.config import AppSettings


@pytest.fixture()
def app_settings(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    """Create AppSettings with no .env file and clean environment."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return AppSettings(_env_file=None)
