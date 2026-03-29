"""Portfolio simulator package for fund-backtest.

Provides the PortfolioSimulator engine and supporting types:
- CostConfig: frozen configuration for transaction and borrow costs
- PortfolioResult: structured output from a backtest simulation run
- PriceFrame: type alias for a date x ticker close-price DataFrame

Usage:
    from fund_backtest.simulator.types import CostConfig, PortfolioResult
    from fund_backtest.simulator.engine import PortfolioSimulator
"""
