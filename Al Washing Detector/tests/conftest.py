"""Shared test fixtures for ai_washer tests."""

import pytest


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch, tmp_path):
    """Set required env vars for tests that load AppSettings."""
    monkeypatch.setenv(
        "AI_WASHER_DATABASE_URL",
        "postgresql+psycopg://localhost:5432/ai_washer_test",
    )
    monkeypatch.setenv("AI_WASHER_EDGAR_IDENTITY", "TestCorp test@example.com")


@pytest.fixture
def scoring_yaml(tmp_path):
    """Create a temporary scoring.yaml for config tests."""
    yaml_content = (
        "weights:\n"
        "  sec_filing: 0.20\n"
        "  patent_gap: 0.15\n"
        "  earnings_call: 0.20\n"
        "  job_posting: 0.25\n"
        "  github_activity: 0.10\n"
        "  compute_spending: 0.10\n"
        "\n"
        "high_risk_threshold: 60\n"
        "low_risk_threshold: 30\n"
    )
    yaml_file = tmp_path / "scoring.yaml"
    yaml_file.write_text(yaml_content)
    return yaml_file
