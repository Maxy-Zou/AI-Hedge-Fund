"""Application configuration loaded from environment variables and .env files.

Uses pydantic-settings for validated, typed configuration. Secrets are loaded
from environment variables (never hardcoded). Default values match the
docker-compose.yml development environment.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application-wide settings loaded from environment and .env file.

    All API keys default to empty string -- the application validates
    required keys at startup, not at config load time. This allows
    partial configuration for development and testing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund"

    # Anthropic
    anthropic_api_key: str = ""

    # Data sources (free tier)
    edgar_identity: str = ""
    finnhub_api_key: str = ""
    fmp_api_key: str = ""
    fred_api_key: str = ""

    # Data sources (paid, add when budget allows)
    polygon_api_key: str = ""
    thetadata_api_key: str = ""

    # Observability
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Token budget defaults (per-tier, matching MODEL_BUDGETS in models.py)
    extraction_token_limit: int = 22_000
    analysis_token_limit: int = 58_000
    reasoning_token_limit: int = 116_000
    pipeline_total_token_limit: int = 500_000

    # Logging
    log_level: str = "INFO"


def get_settings() -> AppSettings:
    """Create a fresh AppSettings instance.

    Returns a new instance each call for testability -- callers can
    override environment before calling.
    """
    return AppSettings()
