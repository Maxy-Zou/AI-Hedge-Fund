"""Pydantic settings for fund-backtest package."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="FUND_BACKTEST_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str
    log_level: str = "INFO"


class UniverseSettings(BaseModel):
    """Universe configuration — loaded from config/universe.yaml."""

    market_cap_min_cents: int = 200_000_000_000   # $2B in cents
    market_cap_max_cents: int = 1_000_000_000_000  # $10B in cents
    seed_url: str = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
    yfinance_delay_secs: float = 1.0
    yfinance_max_retries: int = 3


class PriceSettings(BaseModel):
    """Price data configuration — loaded from config/price.yaml."""

    lookback_years: int = 5
    batch_size: int = 80
    batch_sleep_secs: float = 1.0
    coverage_alert_threshold: float = 0.95
    return_anomaly_threshold: float = 0.50
    max_gap_days: int = 3


_settings: AppSettings | None = None


def load_app_settings() -> AppSettings:
    """Load and cache application settings from environment."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = AppSettings()
    return _settings


def load_universe_settings(config_path: Path | None = None) -> UniverseSettings:
    """Load universe settings from YAML config or return defaults.

    Args:
        config_path: Optional path to a universe.yaml file.
                     If None, returns defaults.

    Returns:
        UniverseSettings with values from YAML or defaults.
    """
    if config_path is None:
        return UniverseSettings()
    try:
        import yaml

        with config_path.open() as f:
            data = yaml.safe_load(f)
        return UniverseSettings(**data.get("universe", {}))
    except Exception:
        return UniverseSettings()


def load_price_settings(config_path: Path | None = None) -> PriceSettings:
    """Load price settings from YAML config or return defaults.

    Args:
        config_path: Optional path to a price.yaml file.
                     If None, returns defaults.

    Returns:
        PriceSettings with values from YAML or defaults.
    """
    if config_path is None:
        return PriceSettings()
    try:
        import yaml

        with config_path.open() as f:
            data = yaml.safe_load(f)
        return PriceSettings(**data.get("price", {}))
    except Exception:
        return PriceSettings()
