"""Tests for Pydantic configuration classes."""

import pytest
from pydantic import ValidationError


def test_app_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("AI_WASHER_DATABASE_URL", "postgresql+psycopg://db:5432/test")
    monkeypatch.setenv("AI_WASHER_EDGAR_IDENTITY", "TestCo test@test.com")
    from ai_washer.config import AppSettings

    settings = AppSettings()
    assert settings.database_url == "postgresql+psycopg://db:5432/test"
    assert settings.edgar_identity == "TestCo test@test.com"


def test_app_settings_requires_database_url(monkeypatch):
    monkeypatch.delenv("AI_WASHER_DATABASE_URL", raising=False)
    monkeypatch.delenv("AI_WASHER_EDGAR_IDENTITY", raising=False)
    from ai_washer.config import AppSettings

    with pytest.raises(ValidationError):
        AppSettings()


def test_signal_weights_default_sum():
    from ai_washer.config import SignalWeights

    w = SignalWeights()
    total = (
        w.sec_filing
        + w.patent_gap
        + w.earnings_call
        + w.job_posting
        + w.github_activity
        + w.compute_spending
    )
    assert abs(total - 1.0) < 0.001


def test_signal_weights_rejects_bad_sum():
    from ai_washer.config import SignalWeights

    with pytest.raises(ValidationError, match="sum"):
        SignalWeights(
            sec_filing=0.50,
            patent_gap=0.50,
            earnings_call=0.50,
            job_posting=0.25,
            github_activity=0.10,
            compute_spending=0.10,
        )


def test_scoring_config_loads_yaml(scoring_yaml, monkeypatch):
    from ai_washer.config import ScoringConfig

    monkeypatch.setenv("AI_WASHER_SCORING_YAML_FILE", str(scoring_yaml))
    config = ScoringConfig(_yaml_file=scoring_yaml)
    assert config.weights.sec_filing == 0.20
    assert config.high_risk_threshold == 60
    assert config.low_risk_threshold == 30


def test_scoring_config_threshold_range():
    from ai_washer.config import ScoringConfig

    with pytest.raises(ValidationError):
        ScoringConfig(high_risk_threshold=150)


def test_configure_logging():
    from ai_washer.logging import configure_logging

    logger = configure_logging("DEBUG")
    assert logger is not None
