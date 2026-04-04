"""Configuration for the Kalshi backtesting engine.

Loads settings from environment variables with KALSHI_BACKTEST_ prefix,
or from a .env file in the working directory. Uses pydantic-settings for
validation and type coercion.

Usage:
    settings = load_settings()
    # or from env only:
    settings = KalshiBacktestSettings()
"""
from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class KalshiBacktestSettings(BaseSettings):
    """All configuration for the backtesting engine.

    Required env vars (no defaults):
        KALSHI_BACKTEST_API_KEY_ID — Kalshi API key identifier
        KALSHI_BACKTEST_PRIVATE_KEY_PATH — path to RSA .pem file

    Optional env vars (defaults shown):
        KALSHI_BACKTEST_API_BASE_URL — defaults to demo API
        KALSHI_BACKTEST_DB_PATH — defaults to kalshi_backtest.duckdb
        KALSHI_BACKTEST_RATE_LIMIT_RPM — defaults to 60
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KALSHI_BACKTEST_",
        extra="ignore",
    )

    api_key_id: str
    private_key_path: Path  # path to RSA .pem file — NOT key content
    api_base_url: str = "https://demo-api.kalshi.co/trade-api/v2"
    db_path: Path = Path("kalshi_backtest.duckdb")
    rate_limit_rpm: int = 60

    @model_validator(mode="after")
    def validate_key_path_extension(self) -> KalshiBacktestSettings:
        """Verify private_key_path has .pem or .key extension — catches common misconfiguration."""
        if self.private_key_path.suffix not in (".pem", ".key"):
            raise ValueError(
                f"private_key_path must point to a .pem file, got: {self.private_key_path}"
            )
        return self


def load_settings() -> KalshiBacktestSettings:
    """Load and validate settings from environment / .env file.

    Raises:
        ValidationError: If required env vars are missing or invalid.
    """
    return KalshiBacktestSettings()  # type: ignore[call-arg]
