"""Type contracts for the Metrics Engine.

Provides:
- _TRADING_DAYS_PER_YEAR: module constant for annualization (252 trading days).
- MetricsBundle: frozen Pydantic model holding all scalar and rolling metrics
  computed from a PortfolioResult.

Usage:
    from fund_backtest.metrics.types import MetricsBundle, _TRADING_DAYS_PER_YEAR

    bundle = MetricsBundle(
        sharpe=1.2, sortino=1.5, calmar=0.8,
        max_drawdown=-0.15, cagr=0.12,
        hit_rate=0.54, win_loss_ratio=1.3, annual_turnover=2.5,
        alpha=0.02, beta=0.95,
        rolling_sharpe=pd.Series(...),
        rolling_drawdown=pd.Series(...),
    )
    # bundle is immutable — any attempt to mutate raises an exception
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel

# Module constant — use this everywhere, never hardcode 252 or 365 inline.
# Daily equity markets trade ~252 days per year. Using 365 inflates
# Sharpe/Sortino by ~20% (sqrt(365)/sqrt(252) = 1.2035).
_TRADING_DAYS_PER_YEAR: int = 252


class MetricsBundle(BaseModel):
    """Full institutional metric suite computed from a PortfolioResult.

    All scalar metrics are floats. Rolling metrics are pd.Series with the
    same DatetimeIndex as PortfolioResult.net_returns. NaN values appear
    before the rolling window fills.

    MetricsBundle is frozen (immutable after construction) to prevent
    accidental mutation during report generation or downstream consumption.

    Args:
        sharpe: Annualized Sharpe ratio (RISK-01). Risk-free rate = 0.0.
        sortino: Annualized Sortino ratio (RISK-01). Uses downside deviation.
        calmar: Calmar ratio = CAGR / abs(max_drawdown) (RISK-01).
        max_drawdown: Maximum drawdown as a negative fraction (RISK-01).
            Convention: negative, e.g. -0.25 means a 25% peak-to-trough loss.
            Pitfall 3 in RESEARCH.md: do NOT flip sign at storage time.
        cagr: Compound annual growth rate as a fraction (RISK-01).
            e.g. 0.15 = 15% annualized return.
        hit_rate: Fraction of profitable trading days (RISK-02).
            Range: [0.0, 1.0]. e.g. 0.54 = 54% of days are profitable.
        win_loss_ratio: Average winning-day return / average losing-day
            magnitude (RISK-02). e.g. 1.3 means wins are 30% larger than losses.
        annual_turnover: Annualized portfolio turnover (RISK-02).
            Computed as sum(abs(weight_changes)) / n_days * 252 from trade_log.
            e.g. 2.5 means the portfolio turns over 2.5x its gross exposure/yr.
        alpha: Annualized alpha vs benchmark (RISK-03).
            Set to 0.0 when benchmark=None.
        beta: Beta vs benchmark (RISK-03).
            Set to 0.0 when benchmark=None.
        rolling_sharpe: Rolling Sharpe ratio Series (RISK-04).
            DatetimeIndex aligned to net_returns. NaN before rolling window fills.
        rolling_drawdown: Rolling maximum drawdown Series (RISK-04).
            DatetimeIndex aligned to net_returns. Values are always <= 0.
            NaN before rolling window fills.
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}
    # arbitrary_types_allowed required for pd.Series fields —
    # Pydantic v2 rejects non-standard types by default (Pitfall 5 in RESEARCH.md).

    # --- Scalar metrics (RISK-01) ---
    sharpe: float
    """Annualized Sharpe ratio. Computed with periods=252 (not qs default 365)."""

    sortino: float
    """Annualized Sortino ratio. Downside deviation in denominator."""

    calmar: float
    """Calmar ratio = CAGR / abs(max_drawdown). Positive when CAGR > 0."""

    max_drawdown: float
    """Maximum drawdown as a negative fraction, e.g. -0.25 for a 25% loss.
    Convention is negative — do not flip sign at storage time."""

    cagr: float
    """Compound annual growth rate as a fraction, e.g. 0.15 = 15%/yr."""

    # --- Trade metrics (RISK-02) ---
    hit_rate: float
    """Fraction of profitable trading days. Range: [0.0, 1.0]."""

    win_loss_ratio: float
    """Average winning-day return / average losing-day magnitude."""

    annual_turnover: float
    """Annualized portfolio turnover derived from trade_log.
    Formula: sum(abs(weight_changes)) / n_days * 252."""

    # --- Benchmark metrics (RISK-03) ---
    alpha: float
    """Annualized alpha vs benchmark. Set to 0.0 when benchmark=None."""

    beta: float
    """Beta vs benchmark (sensitivity to market moves). Set to 0.0 when benchmark=None."""

    # --- Rolling Series (RISK-04) ---
    rolling_sharpe: pd.Series
    """Rolling Sharpe ratio. DatetimeIndex; NaN before rolling window fills."""

    rolling_drawdown: pd.Series
    """Rolling maximum drawdown. DatetimeIndex; values always <= 0.
    NaN before rolling window fills."""
