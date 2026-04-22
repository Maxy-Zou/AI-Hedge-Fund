"""Projected max-drawdown check via historical simulation.

Computes the worst peak-to-trough drawdown the post-trade portfolio would
have experienced over the supplied daily-return history. Pure numpy +
pandas -- no Monte Carlo, no distributional assumption. Historical
simulation captures fat tails and skew better than a parametric VaR for
the paper-portfolio v1 use case (see 06-RESEARCH.md rationale).

Fails CLOSED when any ticker's aligned history is shorter than
``policy.min_history_days`` (Pitfall 4): returns
``(0.0, "insufficient_price_history")`` so ``check_drawdown`` can surface a
named veto. Division-by-zero and NaN sanitisation are explicit guards
(T-06-05); all-zero return series produce drawdown ``0.0`` without raising.

Empty-portfolio candidates are evaluated solo (candidate weight = 1.0)
rather than short-circuited to 0.0 -- that's Pitfall 3 in the research.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import PortfolioSnapshot
from ai_hedge_fund.schemas.risk import Violation


def project_max_drawdown_pct(
    weights: dict[str, float],
    returns: pd.DataFrame,
    policy: RiskPolicy,
) -> tuple[float, str | None]:
    """Project the worst peak-to-trough drawdown (percent) for ``weights``.

    Returns ``(drawdown_pct, error)`` where ``error`` is ``None`` on
    success and ``"insufficient_price_history"`` when any ticker in
    ``weights`` has fewer aligned rows than ``policy.min_history_days``.

    The returned percent is in 0-100 units (e.g., ``15.0`` means 15%).
    """
    if not weights:
        return (0.0, None)

    # Any ticker missing or sparse in the returns frame fails closed
    for ticker in weights:
        if ticker not in returns.columns:
            return (0.0, "insufficient_price_history")
        if int(returns[ticker].count()) < policy.min_history_days:
            return (0.0, "insufficient_price_history")

    aligned = returns[list(weights)].dropna()
    if len(aligned) < policy.min_history_days:
        return (0.0, "insufficient_price_history")

    weight_vec = np.array([weights[t] for t in aligned.columns])
    port_daily_ret = aligned.values @ weight_vec
    equity_curve = np.cumprod(1.0 + port_daily_ret)
    running_max = np.maximum.accumulate(equity_curve)

    # T-06-05 guard: avoid division by zero on degenerate equity curves
    safe_max = np.where(running_max == 0, 1.0, running_max)
    drawdown = (running_max - equity_curve) / safe_max
    drawdown = np.nan_to_num(drawdown, nan=0.0, posinf=0.0, neginf=0.0)

    return (float(np.max(drawdown) * 100.0), None)


def check_drawdown(
    candidate_ticker: str,
    candidate_size_pct: float,
    portfolio: PortfolioSnapshot,
    returns: pd.DataFrame,
    policy: RiskPolicy,
) -> Violation | None:
    """Veto when projected post-trade drawdown exceeds the policy cap.

    Post-trade weights are constructed by scaling pre-trade holdings down
    by ``(1 - candidate_size_fraction)`` and inserting the candidate at its
    fractional weight. For an empty portfolio the candidate becomes 100%
    of the projected portfolio (Pitfall 3 -- do not short-circuit to 0).
    """
    candidate_fraction = candidate_size_pct / 100.0

    if portfolio.total_value_cents == 0:
        weights: dict[str, float] = {candidate_ticker: 1.0}
    else:
        scale = 1.0 - candidate_fraction
        weights = {
            p.ticker: (p.current_value_cents / portfolio.total_value_cents) * scale
            for p in portfolio.positions
        }
        weights[candidate_ticker] = weights.get(candidate_ticker, 0.0) + candidate_fraction

    drawdown_pct, err = project_max_drawdown_pct(weights, returns, policy)

    if err == "insufficient_price_history":
        return Violation(
            name="insufficient_price_history",
            observed=0.0,
            limit=float(policy.min_history_days),
        )

    if drawdown_pct > policy.max_projected_drawdown_pct:
        return Violation(
            name="max_projected_drawdown_pct",
            observed=drawdown_pct,
            limit=policy.max_projected_drawdown_pct,
        )

    return None
