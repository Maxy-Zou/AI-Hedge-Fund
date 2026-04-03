"""Application and Kalshi API configuration loaded from environment variables.

Two settings classes:
- AppSettings: infrastructure config (database, logging) with KALSHI_TRACKER_ prefix
- KalshiSettings: Kalshi API credentials and connection settings with KALSHI_ prefix
"""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Infrastructure configuration (database, logging).

    Loaded from environment variables with KALSHI_TRACKER_ prefix,
    or from a .env file in the working directory.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KALSHI_TRACKER_",
        extra="ignore",
    )

    database_url: str
    log_level: str = "INFO"
    poll_interval_seconds: int = 10   # DATA-02: poll every 5-10s; env: KALSHI_TRACKER_POLL_INTERVAL_SECONDS
    warmup_snapshots: int = 60        # DATA-06: ~10 min baseline at 10s interval; env: KALSHI_TRACKER_WARMUP_SNAPSHOTS

    @field_validator("poll_interval_seconds")
    @classmethod
    def poll_interval_must_be_positive(cls, v: int) -> int:
        """Poll interval must be 1-60 seconds for realistic polling cadence."""
        if v <= 0 or v > 60:
            msg = "poll_interval_seconds must be between 1 and 60"
            raise ValueError(msg)
        return v

    @field_validator("warmup_snapshots")
    @classmethod
    def warmup_snapshots_must_be_positive(cls, v: int) -> int:
        """Warmup threshold must be > 0 — zero warmup bypasses baseline collection."""
        if v <= 0:
            msg = "warmup_snapshots must be > 0"
            raise ValueError(msg)
        return v


class KalshiSettings(BaseSettings):
    """Kalshi API credentials and connection settings.

    Loaded from environment variables with KALSHI_ prefix,
    or from a .env file in the working directory.

    Note: api_base_url defaults to the DEMO API. Set KALSHI_API_BASE_URL
    to https://api.elections.kalshi.com/trade-api/v2 for production trading.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KALSHI_",
        extra="ignore",
    )

    api_key_id: str
    private_key_path: Path  # path to RSA .pem file; NOT the key content
    api_base_url: str = "https://demo-api.kalshi.co/trade-api/v2"  # DEMO by default
    rate_limit_rpm: int = 60  # conservative default; declared as DATA-05 constant
    politics_series: list[str] = [  # allowlist for politics/policy market filtering (DATA-03)
        "PRES",
        "GOV",
        "SENATE",
        "HOUSE",
        "KXELECTION",
    ]

    @field_validator("rate_limit_rpm")
    @classmethod
    def rate_limit_must_be_positive(cls, v: int) -> int:
        """Rate limit must be > 0 to prevent infinite loops in the polling client."""
        if v <= 0:
            msg = "rate_limit_rpm must be > 0"
            raise ValueError(msg)
        return v


def load_app_settings() -> AppSettings:
    """Factory function to create and validate AppSettings from environment."""
    return AppSettings()


def load_kalshi_settings() -> KalshiSettings:
    """Factory function to create and validate KalshiSettings from environment."""
    return KalshiSettings()
