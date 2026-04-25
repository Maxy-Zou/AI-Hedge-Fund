"""Cross-asset correlation check for the Phase 6 risk manager.

Computes the maximum absolute Pearson correlation between a candidate
ticker and any existing portfolio position on daily log returns. A large
positive correlation signals that adding the candidate increases
concentration-like risk even if the position is diversified by sector.

Fails open (returns ``("", 0.0)`` + structlog warning) when portfolio is
empty, when either ticker is missing from the returns dataframe, or when
aligned history is below ``min_window``. Opening is safe here because the
downstream node will also apply the drawdown check, which fails CLOSED on
insufficient data (Pitfall 4).

Threat mitigations:
    T-06-05b: Wrong result on empty / sparse data -- early return with
              structlog warning, unit-tested.
    T-08-12: LLM-authored risk_score -- ``ratio`` is computed in pure
             Python here, surfaced via ``RiskAssessment.utilization``.
"""

from __future__ import annotations

import pandas as pd
import structlog

from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import PortfolioSnapshot
from ai_hedge_fund.schemas.risk import CheckResult, Violation

logger = structlog.get_logger(__name__)


def compute_max_correlation_with_portfolio(
    candidate_ticker: str,
    portfolio_tickers: list[str],
    returns: pd.DataFrame,
    min_window: int = 20,
) -> tuple[str, float]:
    """Return the portfolio ticker most correlated with the candidate.

    Args:
        candidate_ticker: Proposed new position.
        portfolio_tickers: Existing holdings (column names in ``returns``).
        returns: Wide DataFrame of daily log returns, index = business date.
        min_window: Minimum number of aligned rows required to compute the
            correlation matrix. Below this, returns ``("", 0.0)`` and logs
            a warning (fail-open).

    Returns:
        ``(top_ticker, correlation)``. ``correlation`` is the signed Pearson
        value (so both strongly positive and strongly negative pairs bubble
        up -- downstream ``check_correlation`` takes the absolute value).
    """
    # Deduplicate: when the candidate is already in the portfolio, we still
    # want to compare it against OTHER holdings, never against itself.
    other_tickers = [t for t in portfolio_tickers if t != candidate_ticker]
    if not other_tickers:
        return ("", 0.0)

    missing = [t for t in [candidate_ticker, *other_tickers] if t not in returns.columns]
    if missing:
        logger.warning(
            "correlation_ticker_missing",
            missing=missing,
            candidate=candidate_ticker,
        )
        return ("", 0.0)

    aligned = returns[[candidate_ticker, *other_tickers]].dropna()
    if len(aligned) < min_window:
        logger.warning(
            "correlation_insufficient_data",
            window=len(aligned),
            min=min_window,
        )
        return ("", 0.0)

    corrs = aligned.corr()[candidate_ticker].drop(candidate_ticker)
    top_ticker = corrs.abs().idxmax()
    return (str(top_ticker), float(corrs[top_ticker]))


def _safe_ratio(observed: float, limit: float) -> float:
    """Defensive ratio for utilization aggregation.

    Negative observed clamps to 0; non-positive limit falls back to a tiny
    positive epsilon so we never raise or yield ``inf``. See
    ``risk/checks.py::_safe_ratio`` for the same contract on the
    position-size and sector-concentration checks.
    """
    if observed <= 0.0:
        return 0.0
    safe_limit = limit if limit > 0.0 else 1e-9
    return observed / safe_limit


def check_correlation(
    candidate_ticker: str,
    portfolio: PortfolioSnapshot,
    returns: pd.DataFrame,
    policy: RiskPolicy,
) -> CheckResult:
    """Veto when the strongest portfolio correlation exceeds the policy cap.

    Uses absolute correlation so large negative correlations also trigger
    (they contribute to net-exposure risk in a way the cap is meant to
    bound). The observed value reported on the violation is the absolute
    correlation, matching the limit semantics.

    Returns ``CheckResult(ratio, violation)`` -- ``ratio`` is
    ``|corr| / max_correlation_with_portfolio`` even on APPROVED so the
    node can aggregate it into ``RiskAssessment.utilization``.
    """
    _top, corr = compute_max_correlation_with_portfolio(
        candidate_ticker=candidate_ticker,
        portfolio_tickers=portfolio.tickers(),
        returns=returns,
    )
    observed = abs(corr)
    ratio = _safe_ratio(observed, policy.max_correlation_with_portfolio)
    if observed > policy.max_correlation_with_portfolio:
        violation = Violation(
            name="max_correlation_with_portfolio",
            observed=observed,
            limit=policy.max_correlation_with_portfolio,
        )
        return CheckResult(ratio=ratio, violation=violation)
    return CheckResult(ratio=ratio, violation=None)
