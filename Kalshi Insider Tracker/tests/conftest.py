"""Shared pytest fixtures for Kalshi Insider Tracker tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=False)
def kalshi_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set minimal env vars needed for KalshiSettings to load."""
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", "/tmp/fake_key.pem")


@pytest.fixture(autouse=False)
def app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set minimal env vars needed for AppSettings to load."""
    monkeypatch.setenv("KALSHI_TRACKER_DATABASE_URL", "postgresql://test:test@localhost/test")


# --- Daemon test fixtures ---

@pytest.fixture
def mock_kalshi_client() -> MagicMock:
    """Mock KalshiClient that returns empty market list by default."""
    client = MagicMock()
    client.get_politics_markets.return_value = []
    return client


@pytest.fixture
def mock_session() -> MagicMock:
    """Mock SQLAlchemy session."""
    return MagicMock()
