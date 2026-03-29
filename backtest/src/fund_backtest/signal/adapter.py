"""Signal adapter — converts raw strategy scores into portfolio-ready weights.

Provides:
- SignalAdapter: Normalizes a SignalFrame into a WeightFrame ready for the
  backtest engine. Applies look-ahead bias guard (shift(1)), cross-sectional
  rank normalization, min_coverage zeroing, and gross exposure scaling.

Usage::

    from fund_backtest.signal.adapter import SignalAdapter
    from fund_backtest.config import SignalAdapterConfig

    adapter = SignalAdapter()                         # defaults
    adapter = SignalAdapter(SignalAdapterConfig(...)) # custom config
    weight_frame = adapter.adapt(signal_frame)

CRITICAL: The WeightFrame returned already has shift(1) applied.
Phase 4 Portfolio Simulator must NOT apply an additional shift.
"""

from __future__ import annotations

import pandas as pd
import structlog

from fund_backtest.config import SignalAdapterConfig
from fund_backtest.signal.types import SignalFrame, WeightFrame
from fund_backtest.signal.validator import validate_signal_frame

logger = structlog.get_logger(__name__)


class SignalAdapter:
    """Normalizes raw strategy scores into portfolio-ready WeightFrame.

    Pipeline steps (in order):
      1. validate_signal_frame(signal) — raises SignalValidationError on bad input
      2. Drop all-NaN columns with structlog warning
      3. Cross-sectional rank: signal.rank(axis=1, pct=True) -> [0, 1]
      4. Map to weights: 2 * ranks - 1 -> (-1, +1]
      5. Clip to [-1.0, +1.0] (handles float edge cases)
      6. Zero out rows where non-NaN count < config.min_coverage
      7. Scale rows where abs().sum() > config.gross_exposure_limit (proportional)
      8. Apply shift(1) — WeightFrame row T carries T-1 signal (look-ahead bias guard)

    CRITICAL: Phase 4 Portfolio Simulator must NOT apply an additional shift.
    The WeightFrame returned is already temporally safe.
    """

    def __init__(self, config: SignalAdapterConfig | None = None) -> None:
        """Initialise with optional config (defaults to SignalAdapterConfig())."""
        self._config = config or SignalAdapterConfig()
        self._log = logger.bind(component="signal_adapter")

    def adapt(self, signal: SignalFrame) -> WeightFrame:
        """Convert raw SignalFrame to portfolio-ready WeightFrame.

        Returns a new DataFrame. Input is never modified.
        First row of returned WeightFrame is always NaN (shift artifact).

        Args:
            signal: Raw strategy scores as a SignalFrame (DatetimeIndex, ticker columns).

        Returns:
            WeightFrame with values in [-1.0, +1.0], already shifted(1).
            First row is all-NaN by design (no prior signal available).

        Raises:
            SignalValidationError: If signal does not satisfy the SignalFrame contract.
        """
        # Step 1: validate contract — raises SignalValidationError on violation
        validate_signal_frame(signal)

        # Step 2: drop all-NaN columns
        cleaned = self._drop_all_nan_columns(signal)

        # Step 3 & 4 & 5: rank -> map -> clip
        ranks = cleaned.rank(axis=1, pct=True)
        weights = self._compute_weights(ranks)

        # Step 6: zero out rows below min_coverage threshold
        weights = self._zero_low_coverage_rows(weights)

        # Step 7: scale rows that exceed gross exposure limit
        weights = self._scale_gross_exposure(weights)

        # Step 8: shift(1) — look-ahead bias guard
        return weights.shift(1)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _drop_all_nan_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop columns where every value is NaN, logging a warning for each.

        Args:
            df: Input DataFrame (not mutated).

        Returns:
            New DataFrame with all-NaN columns removed.
        """
        all_nan_cols = [col for col in df.columns if df[col].isna().all()]
        if all_nan_cols:
            for col in all_nan_cols:
                self._log.warning("signal_adapter_dropping_all_nan_column", column=col)
        return df.drop(columns=all_nan_cols)

    def _compute_weights(self, ranks: pd.DataFrame) -> pd.DataFrame:
        """Map percentile ranks [0, 1] to weights in (-1, +1], then clip.

        Formula: weight = 2 * rank - 1, then clip(-1.0, 1.0).

        Args:
            ranks: Percentile ranks from DataFrame.rank(pct=True).

        Returns:
            New DataFrame with values clipped to [-1.0, +1.0].
        """
        return (2 * ranks - 1).clip(-1.0, 1.0)

    def _zero_low_coverage_rows(self, weights: pd.DataFrame) -> pd.DataFrame:
        """Zero out rows where non-NaN ticker count falls below min_coverage.

        Rows are zeroed (not dropped) to preserve the DatetimeIndex alignment.

        Args:
            weights: Weight DataFrame after rank normalization.

        Returns:
            New DataFrame with low-coverage rows set to 0.0.
        """
        non_nan_count = weights.notna().sum(axis=1)
        result = weights.copy()
        result.loc[non_nan_count < self._config.min_coverage] = 0.0
        return result

    def _scale_gross_exposure(self, weights: pd.DataFrame) -> pd.DataFrame:
        """Scale rows proportionally where abs(weight sum) exceeds gross_exposure_limit.

        Args:
            weights: Weight DataFrame after coverage zeroing.

        Returns:
            New DataFrame with gross exposure capped at config.gross_exposure_limit.
        """
        abs_sum = weights.abs().sum(axis=1)
        needs_scaling = abs_sum > self._config.gross_exposure_limit
        # Where scaling is needed: scale factor = limit / abs_sum; otherwise 1.0
        scale_factor = self._config.gross_exposure_limit / abs_sum.where(needs_scaling, 1.0)
        return weights.mul(scale_factor, axis=0)
