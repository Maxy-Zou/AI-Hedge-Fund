"""Tests for AppSettings and KalshiSettings configuration models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kalshi_tracker.config import AppSettings, KalshiSettings


def test_app_settings_loads_database_url(app_env: None) -> None:
    """AppSettings loads database_url from KALSHI_TRACKER_DATABASE_URL env var."""
    settings = AppSettings()
    assert settings.database_url == "postgresql://test:test@localhost/test"


def test_app_settings_missing_database_url_raises() -> None:
    """AppSettings raises ValidationError when DATABASE_URL is not set."""
    with pytest.raises(ValidationError):
        AppSettings()


def test_kalshi_settings_default_rate_limit_rpm(kalshi_env: None) -> None:
    """KalshiSettings defaults rate_limit_rpm to 60 (DATA-05 conservative limit)."""
    settings = KalshiSettings()
    assert settings.rate_limit_rpm == 60


def test_kalshi_settings_rate_limit_must_be_positive(kalshi_env: None) -> None:
    """KalshiSettings rejects rate_limit_rpm <= 0 to prevent infinite loops."""
    with pytest.raises(ValidationError):
        KalshiSettings(rate_limit_rpm=0)


def test_kalshi_settings_private_key_path_is_path_type(kalshi_env: None) -> None:
    """KalshiSettings coerces private_key_path string to pathlib.Path."""
    from pathlib import Path

    settings = KalshiSettings()
    assert isinstance(settings.private_key_path, Path)


def test_kalshi_settings_default_api_base_url_is_demo(kalshi_env: None) -> None:
    """KalshiSettings defaults api_base_url to demo API (safety constraint)."""
    settings = KalshiSettings()
    assert "demo" in settings.api_base_url
