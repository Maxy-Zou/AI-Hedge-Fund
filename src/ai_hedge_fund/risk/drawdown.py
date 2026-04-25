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

Threat mitigations:
    T-08-12: LLM-authored risk_score -- the per-check ``ratio`` returned
             on :class:`CheckResult` is computed in pure Python here and
             aggregated into ``RiskAssessment.utilization``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import PortfolioSnapshot
from ai_hedge_fund.schemas.risk import CheckResult, Violation


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


def _safe_ratio(observed: float, limit: float) -> float:
    """Defensive ratio for utilization aggregation.

    See ``risk/checks.py::_safe_ratio`` for the same contract on the
    position-size and sector-concentration checks.
    """
    if observed <= 0.0:
        return 0.0
    safe_limit = limit if limit > 0.0 else 1e-9
    return observed / safe_limit


def check_drawdown(
    candidate_ticker: str,
    candidate_size_pct: float,
    portfolio: PortfolioSnapshot,
    returns: pd.DataFrame,
    policy: RiskPolicy,
) -> CheckResult:
    """Veto when projected post-trade drawdown exceeds the policy cap.

    Post-trade weights are constructed by scaling pre-trade holdings down
    by ``(1 - candidate_size_fraction)`` and inserting the candidate at its
    fractional weight. For an empty portfolio the candidate becomes 100%
    of the projected portfolio (Pitfall 3 -- do not short-circuit to 0).

    Returns ``CheckResult(ratio, violation)``. On the
    ``insufficient_price_history`` branch ``ratio`` is ``1.0`` -- treating
    the candidate as fully consuming the policy's data-quality budget so
    the assessment's ``utilization`` reflects the fail-closed outcome. On
    the success branch ``ratio`` is ``drawdown / max_projected_drawdown``.
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
        violation = Violation(
            name="insufficient_price_history",
            observed=0.0,
            limit=float(policy.min_history_days),
        )
        # Fail-closed: utilization saturates so the upstream assessment
        # records that the data-quality budget was fully consumed.
        return CheckResult(ratio=1.0, violation=violation)

    ratio = _safe_ratio(drawdown_pct, policy.max_projected_drawdown_pct)

    if drawdown_pct > policy.max_projected_drawdown_pct:
        violation = Violation(
            name="max_projected_drawdown_pct",
            observed=drawdown_pct,
            limit=policy.max_projected_drawdown_pct,
        )
        return CheckResult(ratio=ratio, violation=violation)

    return CheckResult(ratio=ratio, violation=None)
