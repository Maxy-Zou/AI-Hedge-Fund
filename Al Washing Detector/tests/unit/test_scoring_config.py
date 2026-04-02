"""Tests for scoring sub-config classes (SecFilingScoringConfig, ComputeSpendingScoringConfig).

Covers defaults, validation bounds, YAML loading, and ScoringConfig nesting.
"""

import pytest
from pydantic import ValidationError


class TestSecFilingScoringConfig:
    """Tests for SecFilingScoringConfig defaults and validation."""

    def test_defaults(self):
        from ai_washer.config import SecFilingScoringConfig

        cfg = SecFilingScoringConfig()
        assert cfg.section_weights == {"mda": 0.50, "risk_factors": 0.20, "business": 0.30}
        assert cfg.window_years == 3
        assert cfg.sigmoid_midpoint == 1.0
        assert cfg.sigmoid_steepness == 2.0

    def test_window_years_rejects_zero(self):
        from ai_washer.config import SecFilingScoringConfig

        with pytest.raises(ValidationError):
            SecFilingScoringConfig(window_years=0)

    def test_window_years_rejects_eleven(self):
        from ai_washer.config import SecFilingScoringConfig

        with pytest.raises(ValidationError):
            SecFilingScoringConfig(window_years=11)

    def test_window_years_accepts_boundary_values(self):
        from ai_washer.config import SecFilingScoringConfig

        cfg_min = SecFilingScoringConfig(window_years=1)
        assert cfg_min.window_years == 1

        cfg_max = SecFilingScoringConfig(window_years=10)
        assert cfg_max.window_years == 10

    def test_custom_section_weights(self):
        from ai_washer.config import SecFilingScoringConfig

        custom_weights = {"mda": 0.70, "risk_factors": 0.10, "business": 0.20}
        cfg = SecFilingScoringConfig(section_weights=custom_weights)
        assert cfg.section_weights == custom_weights


class TestComputeSpendingScoringConfig:
    """Tests for ComputeSpendingScoringConfig defaults and validation."""

    def test_defaults(self):
        from ai_washer.config import ComputeSpendingScoringConfig

        cfg = ComputeSpendingScoringConfig()
        assert cfg.capex_weight == 0.70
        assert cfg.cloud_mention_weight == 0.30
        assert cfg.window_years == 3
        assert cfg.sigmoid_midpoint == 1.0
        assert cfg.sigmoid_steepness == 2.0

    def test_capex_weight_rejects_above_one(self):
        from ai_washer.config import ComputeSpendingScoringConfig

        with pytest.raises(ValidationError):
            ComputeSpendingScoringConfig(capex_weight=1.5)

    def test_capex_weight_rejects_negative(self):
        from ai_washer.config import ComputeSpendingScoringConfig

        with pytest.raises(ValidationError):
            ComputeSpendingScoringConfig(capex_weight=-0.1)

    def test_cloud_mention_weight_rejects_above_one(self):
        from ai_washer.config import ComputeSpendingScoringConfig

        with pytest.raises(ValidationError):
            ComputeSpendingScoringConfig(cloud_mention_weight=1.5)

    def test_window_years_rejects_zero(self):
        from ai_washer.config import ComputeSpendingScoringConfig

        with pytest.raises(ValidationError):
            ComputeSpendingScoringConfig(window_years=0)

    def test_capex_weight_accepts_boundary_values(self):
        from ai_washer.config import ComputeSpendingScoringConfig

        cfg_zero = ComputeSpendingScoringConfig(capex_weight=0.0)
        assert cfg_zero.capex_weight == 0.0

        cfg_one = ComputeSpendingScoringConfig(capex_weight=1.0)
        assert cfg_one.capex_weight == 1.0


class TestScoringConfigNested:
    """Tests for ScoringConfig with nested sec_filing and compute_spending sub-configs."""

    def test_nested_defaults(self):
        from ai_washer.config import ScoringConfig

        cfg = ScoringConfig()
        assert hasattr(cfg, "sec_filing")
        assert hasattr(cfg, "compute_spending")
        assert cfg.sec_filing.window_years == 3
        assert cfg.compute_spending.capex_weight == 0.70

    def test_nested_sec_filing_type(self):
        from ai_washer.config import ScoringConfig, SecFilingScoringConfig

        cfg = ScoringConfig()
        assert isinstance(cfg.sec_filing, SecFilingScoringConfig)

    def test_nested_compute_spending_type(self):
        from ai_washer.config import ComputeSpendingScoringConfig, ScoringConfig

        cfg = ScoringConfig()
        assert isinstance(cfg.compute_spending, ComputeSpendingScoringConfig)

    def test_loads_from_yaml(self, scoring_yaml_extended):
        from ai_washer.config import ScoringConfig

        cfg = ScoringConfig(_yaml_file=scoring_yaml_extended)
        assert cfg.sec_filing.window_years == 3
        assert cfg.sec_filing.section_weights == {
            "mda": 0.50,
            "risk_factors": 0.20,
            "business": 0.30,
        }
        assert cfg.compute_spending.capex_weight == 0.70
        assert cfg.compute_spending.cloud_mention_weight == 0.30


@pytest.fixture
def scoring_yaml_extended(tmp_path):
    """Create a temporary scoring.yaml with sec_filing and compute_spending sections."""
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
        "\n"
        "sec_filing:\n"
        "  section_weights:\n"
        "    mda: 0.50\n"
        "    risk_factors: 0.20\n"
        "    business: 0.30\n"
        "  window_years: 3\n"
        "  sigmoid_midpoint: 1.0\n"
        "  sigmoid_steepness: 2.0\n"
        "\n"
        "compute_spending:\n"
        "  capex_weight: 0.70\n"
        "  cloud_mention_weight: 0.30\n"
        "  window_years: 3\n"
        "  sigmoid_midpoint: 1.0\n"
        "  sigmoid_steepness: 2.0\n"
    )
    yaml_file = tmp_path / "scoring.yaml"
    yaml_file.write_text(yaml_content)
    return yaml_file
