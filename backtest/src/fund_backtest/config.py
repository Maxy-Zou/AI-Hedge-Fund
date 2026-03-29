"""Pydantic settings for fund-backtest package."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from fund_backtest.simulator.types import CostConfig


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

    market_cap_min_cents: int = 200_000_000_000  # $2B in cents
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


class SignalAdapterConfig(BaseModel):
    """Signal adapter configuration — controls normalization and coverage rules.

    Fields:
        min_coverage: Minimum number of tickers with non-NaN signals required
                      for a date row to be included in the output WeightFrame.
                      Rows with fewer non-NaN values are dropped before normalization.
        gross_exposure_limit: Maximum absolute sum of portfolio weights allowed
                              after normalization. Controls total leverage.
                              1.0 = fully invested, 2.0 = 2x leverage.
    """

    min_coverage: int = 5
    """Minimum non-NaN tickers per row. Rows below this threshold are dropped."""

    gross_exposure_limit: float = 1.0
    """Maximum absolute weight sum after normalization (e.g. 1.0 = no leverage)."""


def load_signal_adapter_config(config_path: Path | None = None) -> SignalAdapterConfig:
    """Load signal adapter config from YAML config or return defaults.

    Args:
        config_path: Optional path to a signal.yaml file.
                     If None, returns defaults.

    Returns:
        SignalAdapterConfig with values from YAML or defaults.
    """
    if config_path is None:
        return SignalAdapterConfig()
    try:
        import yaml

        with config_path.open() as f:
            data = yaml.safe_load(f)
        return SignalAdapterConfig(**data.get("signal_adapter", {}))
    except Exception:
        return SignalAdapterConfig()


def load_cost_config(config_path: Path | None = None) -> CostConfig:
    """Load cost config from YAML config or return defaults.

    Args:
        config_path: Optional path to a cost.yaml file.
                     If None, returns defaults.

    Returns:
        CostConfig with values from YAML or defaults.
    """
    if config_path is None:
        return CostConfig()
    try:
        import yaml

        with config_path.open() as f:
            data = yaml.safe_load(f)
        return CostConfig(**data.get("cost", {}))
    except Exception:
        return CostConfig()


class MetricsConfig(BaseModel):
    """Metrics engine configuration — controls rolling windows and annualization.

    Fields:
        rolling_window: Rolling window in trading days for rolling_sharpe
                        and rolling_drawdown. Default 252 (one trading year).
        periods_per_year: Trading days per year for annualization.
                          CRITICAL: must be 252 (not 365). Using 365 inflates
                          Sharpe/Sortino by ~20% on daily equity data.
        risk_free_rate: Daily risk-free rate for Sharpe/Sortino computation.
                        Default 0.0 (no RF subtraction).
    """

    rolling_window: int = 252
    """Rolling window in trading days. Default: 252 (one trading year)."""

    periods_per_year: int = 252
    """Annualization period. Use 252 for daily equity data (NOT 365)."""

    risk_free_rate: float = 0.0
    """Daily risk-free rate for Sharpe/Sortino. Default: 0.0."""


def load_metrics_config(config_path: Path | None = None) -> MetricsConfig:
    """Load metrics config from YAML 'metrics' key or return defaults.

    Args:
        config_path: Optional path to a metrics.yaml file.
                     If None, returns defaults.

    Returns:
        MetricsConfig with values from YAML or defaults.
    """
    if config_path is None:
        return MetricsConfig()
    try:
        import yaml

        with config_path.open() as f:
            data = yaml.safe_load(f)
        return MetricsConfig(**data.get("metrics", {}))
    except Exception:
        return MetricsConfig()
