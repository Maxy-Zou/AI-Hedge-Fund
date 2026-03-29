"""Type contracts for the Portfolio Simulator.

Provides:
- PriceFrame: type alias for a date x ticker close-price DataFrame (dollars).
- CostConfig: frozen Pydantic model holding cost parameters (slippage, commission, borrow).
- PortfolioResult: Pydantic model for simulation output (gross/net returns, positions, trade log).

Usage:
    from fund_backtest.simulator.types import CostConfig, PortfolioResult, PriceFrame

    cost = CostConfig(slippage_bps=5.0)
    # cost is immutable — any attempt to mutate raises a ValidationError
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, Field

# PriceFrame: date x ticker float close prices in dollars (not cents).
#
# Schema contract:
#   index   : pd.DatetimeIndex — one row per trading date.
#   columns : str — ticker symbols (e.g. "AAPL", "MSFT").
#   values  : float — adjusted close price in USD.
#
# Produced by: price data pipeline (Phase 2).
# Consumed by: PortfolioSimulator.simulate().
PriceFrame = pd.DataFrame


class CostConfig(BaseModel):
    """Cost parameters for the portfolio simulator.

    All costs are expressed in basis points (bps) where 1 bps = 0.01%.
    CostConfig is frozen (immutable after construction) to prevent accidental
    mutation during a simulation run.

    Args:
        slippage_bps: One-way slippage per trade in basis points.
                      Applied on each weight change (entry and exit).
        commission_bps: One-way commission per trade in basis points.
                        Applied on each weight change (entry and exit).
        borrow_cost_bps_annual: Annualized short borrow cost in basis points.
                                Applied daily as a fraction (bps / 10000 / 252)
                                on the absolute value of each short position weight.

    Example:
        >>> cost = CostConfig(slippage_bps=10.0, commission_bps=5.0)
        >>> cost.slippage_bps
        10.0
    """

    model_config = {"frozen": True}

    slippage_bps: float = Field(default=10.0, ge=0.0)
    """One-way slippage per trade in bps (10 bps = 0.10%)."""

    commission_bps: float = Field(default=5.0, ge=0.0)
    """One-way commission per trade in bps (5 bps = 0.05%)."""

    borrow_cost_bps_annual: float = Field(default=50.0, ge=0.0)
    """Annualized short borrow cost in bps (50 bps = 0.50%/yr).
    Flat rate — tiered borrow is a future enhancement."""


class PortfolioResult(BaseModel):
    """Structured output from a single backtest simulation run.

    Holds both gross and net return series alongside the full position
    history and a trade-level cost log for attribution and debugging.

    Args:
        gross_returns: Daily gross returns before cost deduction.
        net_returns: Daily net returns after all costs.
        positions: Portfolio weight held each day.
        trade_log: Per-trade cost detail for attribution analysis.
    """

    model_config = {"arbitrary_types_allowed": True}

    gross_returns: pd.Series
    """Daily gross returns before cost deduction. DatetimeIndex. Leading NaN row dropped."""

    net_returns: pd.Series
    """Daily net returns after all costs. DatetimeIndex. Same length as gross_returns."""

    positions: pd.DataFrame
    """Date x ticker weight held each day. Same shape as input WeightFrame (minus NaN row)."""

    trade_log: pd.DataFrame
    """Columns: date, ticker, direction (long/short), weight_before, weight_after,
    weight_change, cost_fraction, cost_bps."""
