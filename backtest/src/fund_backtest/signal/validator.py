"""Validation for SignalFrame inputs.

Provides:
- SignalValidationError: Raised when a SignalFrame fails contract validation.
- validate_signal_frame(): Validates a pd.DataFrame against the SignalFrame contract.

Call validate_signal_frame() at the adapter boundary before any normalization
to catch contract violations early with descriptive error messages.
"""

from __future__ import annotations

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class SignalValidationError(ValueError):
    """Raised when a SignalFrame fails contract validation.

    Always includes a descriptive message naming the exact violation so the
    caller can identify which strategy module produced the invalid signal.
    """


def validate_signal_frame(signal: pd.DataFrame) -> None:
    """Validate a DataFrame against the SignalFrame contract.

    Checks the index type, column presence, and column name types in order,
    raising on the first violation. All-NaN columns are warned about but
    not treated as errors (they may be excluded downstream by the adapter).

    Args:
        signal: A pd.DataFrame to validate against the SignalFrame contract.

    Returns:
        None if the frame passes all checks.

    Raises:
        SignalValidationError: If any contract invariant is violated.
    """
    # 1. Index must be DatetimeIndex
    if not isinstance(signal.index, pd.DatetimeIndex):
        raise SignalValidationError(
            f"SignalFrame.index must be DatetimeIndex, got {type(signal.index).__name__}"
        )

    # 2. At least one ticker column must be present
    if signal.columns.empty:
        raise SignalValidationError("SignalFrame must have at least one ticker column")

    # 3. All column names must be non-empty strings
    if not all(isinstance(c, str) and c for c in signal.columns):
        raise SignalValidationError("All SignalFrame column names must be non-empty strings")

    # 4. Warn (do not raise) on all-NaN columns — adapter will drop them
    all_nan_cols = [col for col in signal.columns if signal[col].isna().all()]
    if all_nan_cols:
        logger.warning(
            "signal_frame_all_nan_columns",
            columns=all_nan_cols,
            count=len(all_nan_cols),
        )
