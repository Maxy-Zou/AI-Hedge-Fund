"""Pydantic settings classes for environment and YAML configuration."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables with AI_WASHER_ prefix."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AI_WASHER_",
        extra="ignore",
    )

    database_url: str
    edgar_identity: str
    github_token: str = ""
    patentsview_api_key: str = ""
    patentsview_base_url: str = "https://search.patentsview.org/api/v1"
    earningscall_api_key: str = ""
    log_level: str = "INFO"


class SignalWeights(BaseModel):
    """Signal weights for composite scoring. All weights must sum to 1.0."""

    sec_filing: float = 0.20
    patent_gap: float = 0.15
    earnings_call: float = 0.20
    job_posting: float = 0.25
    github_activity: float = 0.10
    compute_spending: float = 0.10

    @model_validator(mode="after")
    def _check_weights_sum(self) -> SignalWeights:
        total = (
            self.sec_filing
            + self.patent_gap
            + self.earnings_call
            + self.job_posting
            + self.github_activity
            + self.compute_spending
        )
        if abs(total - 1.0) > 0.001:
            msg = f"Signal weights must sum to 1.0 (got {total:.4f})"
            raise ValueError(msg)
        return self


class UniverseSettings(BaseModel):
    """Universe builder configuration.

    Per D-04/D-05/Pitfall 2: market cap thresholds are widened from the
    nominal $2B-$10B target range to $1.5B-$9B to account for the
    EntityPublicFloat proxy approximation in XBRL data.
    """

    efts_page_size: int = Field(default=50, ge=10, le=100)
    market_cap_min_cents: int = Field(default=150_000_000_000)  # $1.5B (widened per Pitfall 2)
    market_cap_max_cents: int = Field(default=900_000_000_000)  # $9B (widened per Pitfall 2)
    ai_keywords: list[str] = Field(
        default_factory=lambda: ["artificial intelligence", "machine learning"]
    )
    fuzzy_match_threshold: int = Field(default=85, ge=50, le=100)
    refresh_cadence_days: int = Field(default=30, ge=1)


class FilingCollectionSettings(BaseModel):
    """Configuration for SEC filing collection.

    Controls which form types to collect, text size limits for storage,
    and maximum filing counts per type.
    """

    form_types: list[str] = Field(default_factory=lambda: ["10-K", "10-Q", "8-K"])
    section_max_chars: int = Field(default=50_000, ge=1000)
    max_8k_filings: int = Field(default=10, ge=1, le=50)
    max_annual_filings: int = Field(default=5, ge=1, le=20)
    max_quarterly_filings: int = Field(default=8, ge=1, le=40)


class SecFilingScoringConfig(BaseModel):
    """Configuration for SEC filing mismatch scoring per D-01/D-03.

    Controls section weights, growth window size, and sigmoid normalization
    parameters for the SEC filing mismatch signal.
    """

    section_weights: dict[str, float] = Field(
        default_factory=lambda: {"mda": 0.50, "risk_factors": 0.20, "business": 0.30}
    )
    window_years: int = Field(default=3, ge=1, le=10)
    sigmoid_midpoint: float = Field(default=1.0)
    sigmoid_steepness: float = Field(default=2.0)


class ComputeSpendingScoringConfig(BaseModel):
    """Configuration for compute spending gap scoring per D-05.

    Controls CapEx/cloud weighting, growth window, and sigmoid normalization
    for the compute spending gap signal.
    """

    capex_weight: float = Field(default=0.70, ge=0.0, le=1.0)
    cloud_mention_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    window_years: int = Field(default=3, ge=1, le=10)
    sigmoid_midpoint: float = Field(default=1.0)
    sigmoid_steepness: float = Field(default=2.0)


class PatentGapScoringConfig(BaseModel):
    """Configuration for patent gap scoring.

    Controls growth window size and sigmoid normalization parameters
    for the patent gap signal.
    """

    window_years: int = Field(default=3, ge=1, le=10)
    sigmoid_midpoint: float = Field(default=1.0)
    sigmoid_steepness: float = Field(default=2.0)


class EarningsVaguenessScoringConfig(BaseModel):
    """Configuration for earnings call vagueness scoring.

    Controls buzzword vs sentiment weighting and sigmoid normalization
    parameters for the earnings call vagueness signal.
    """

    buzzword_weight: float = Field(default=0.70, ge=0.0, le=1.0)
    sentiment_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    sigmoid_midpoint: float = Field(default=1.0)
    sigmoid_steepness: float = Field(default=2.0)

    @model_validator(mode="after")
    def _check_weights_sum(self) -> EarningsVaguenessScoringConfig:
        total = self.buzzword_weight + self.sentiment_weight
        if abs(total - 1.0) > 0.001:
            msg = f"buzzword_weight + sentiment_weight must sum to 1.0 (got {total:.4f})"
            raise ValueError(msg)
        return self


class JobMismatchScoringConfig(BaseModel):
    """Configuration for job posting mismatch scoring.

    Controls ghost job detection threshold, and weighting between ghost penalty,
    engineering ratio, and hiring intensity sub-signals.
    """

    ghost_days_threshold: int = Field(default=90, ge=30, le=365)
    ghost_penalty_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    engineering_weight: float = Field(default=0.40, ge=0.0, le=1.0)
    hiring_intensity_weight: float = Field(default=0.40, ge=0.0, le=1.0)
    sigmoid_midpoint: float = Field(default=1.0)
    sigmoid_steepness: float = Field(default=2.0)


class GitHubActivityScoringConfig(BaseModel):
    """Configuration for GitHub activity scoring.

    Controls maximum repos to scan per org, recency decay window,
    and sigmoid normalization parameters for the GitHub activity signal.
    """

    max_repos_per_org: int = Field(default=100, ge=10, le=500)
    recency_decay_days: int = Field(default=365, ge=30, le=730)
    sigmoid_midpoint: float = Field(default=1.0)
    sigmoid_steepness: float = Field(default=2.0)


class ScoringConfig(BaseSettings):
    """Scoring configuration loaded from YAML file."""

    model_config = SettingsConfigDict(
        yaml_file="config/scoring.yaml",
        extra="ignore",
    )

    _default_yaml: ClassVar[str] = "config/scoring.yaml"

    weights: SignalWeights = Field(default_factory=SignalWeights)
    high_risk_threshold: int = Field(default=60, ge=0, le=100)
    low_risk_threshold: int = Field(default=30, ge=0, le=100)
    strong_short_threshold: int = Field(default=80, ge=0, le=100)
    sec_filing: SecFilingScoringConfig = Field(default_factory=SecFilingScoringConfig)
    compute_spending: ComputeSpendingScoringConfig = Field(
        default_factory=ComputeSpendingScoringConfig
    )
    patent_gap: PatentGapScoringConfig = Field(default_factory=PatentGapScoringConfig)
    github_activity: GitHubActivityScoringConfig = Field(
        default_factory=GitHubActivityScoringConfig
    )
    earnings_vagueness: EarningsVaguenessScoringConfig = Field(
        default_factory=EarningsVaguenessScoringConfig
    )
    job_mismatch: JobMismatchScoringConfig = Field(
        default_factory=JobMismatchScoringConfig
    )

    def __init__(self, _yaml_file: Path | str | None = None, **kwargs):
        """Allow overriding yaml_file path for testing."""
        if _yaml_file is not None:
            kwargs.setdefault("_secrets_dir", None)
            # Store for settings_customise_sources to pick up
            self.__class__._override_yaml = str(_yaml_file)
        super().__init__(**kwargs)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        from pydantic_settings import YamlConfigSettingsSource

        yaml_file = getattr(cls, "_override_yaml", None) or cls._default_yaml

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=yaml_file),
            file_secret_settings,
        )


def load_app_settings() -> AppSettings:
    """Factory function to create AppSettings."""
    return AppSettings()


def load_scoring_config() -> ScoringConfig:
    """Factory function to create ScoringConfig."""
    return ScoringConfig()
