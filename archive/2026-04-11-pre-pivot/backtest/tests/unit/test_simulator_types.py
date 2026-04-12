"""TDD tests for CostConfig and PortfolioResult type contracts.

Tests for:
- CostConfig default values (slippage_bps, commission_bps, borrow_cost_bps_annual)
- CostConfig Pydantic validation (negative bps rejected, fractional bps accepted)
- CostConfig frozen enforcement (mutation raises exception)
- PortfolioResult construction with pandas fields
"""

from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from fund_backtest.simulator.types import CostConfig, PortfolioResult


class TestCostConfigDefaults:
    """CostConfig() must return correct default values for all three cost fields."""

    def test_default_values(self) -> None:
        """CostConfig() defaults: slippage=10.0, commission=5.0, borrow=50.0."""
        cfg = CostConfig()
        assert cfg.slippage_bps == 10.0
        assert cfg.commission_bps == 5.0
        assert cfg.borrow_cost_bps_annual == 50.0


class TestCostConfigValidation:
    """CostConfig must reject negative bps and accept fractional/zero values."""

    def test_negative_slippage_raises(self) -> None:
        """CostConfig(slippage_bps=-1.0) must raise ValidationError."""
        with pytest.raises(ValidationError):
            CostConfig(slippage_bps=-1.0)

    def test_negative_commission_raises(self) -> None:
        """CostConfig(commission_bps=-0.01) must raise ValidationError."""
        with pytest.raises(ValidationError):
            CostConfig(commission_bps=-0.01)

    def test_negative_borrow_raises(self) -> None:
        """CostConfig(borrow_cost_bps_annual=-50.0) must raise ValidationError."""
        with pytest.raises(ValidationError):
            CostConfig(borrow_cost_bps_annual=-50.0)

    def test_fractional_bps_accepted(self) -> None:
        """CostConfig(slippage_bps=7.5) must not raise — fractional bps is valid."""
        cfg = CostConfig(slippage_bps=7.5)
        assert cfg.slippage_bps == 7.5

    def test_zero_bps_accepted(self) -> None:
        """CostConfig with all-zero bps must not raise — zero is a valid (no-cost) config."""
        cfg = CostConfig(slippage_bps=0.0, commission_bps=0.0, borrow_cost_bps_annual=0.0)
        assert cfg.slippage_bps == 0.0
        assert cfg.commission_bps == 0.0
        assert cfg.borrow_cost_bps_annual == 0.0


class TestCostConfigFrozen:
    """CostConfig must be immutable — mutation attempts must raise an exception."""

    def test_mutation_raises(self) -> None:
        """Assigning cfg.slippage_bps = 99.0 must raise ValidationError or TypeError."""
        cfg = CostConfig()
        with pytest.raises((ValidationError, TypeError)):
            cfg.slippage_bps = 99.0  # type: ignore[misc]


class TestPortfolioResultStructure:
    """PortfolioResult must accept pandas Series and DataFrame fields."""

    def test_construction(self) -> None:
        """PortfolioResult can be constructed with pd.Series gross/net_returns
        and pd.DataFrame positions/trade_log."""
        gross = pd.Series([0.01, 0.02], dtype=float)
        net = pd.Series([0.009, 0.018], dtype=float)
        positions = pd.DataFrame({"AAPL": [0.5, 0.5]})
        trade_log = pd.DataFrame()

        result = PortfolioResult(
            gross_returns=gross,
            net_returns=net,
            positions=positions,
            trade_log=trade_log,
        )
        assert isinstance(result.gross_returns, pd.Series)
        assert isinstance(result.net_returns, pd.Series)
        assert isinstance(result.positions, pd.DataFrame)
        assert isinstance(result.trade_log, pd.DataFrame)
