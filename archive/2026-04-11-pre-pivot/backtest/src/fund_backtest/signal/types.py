"""Type aliases for the signal module.

Provides:
- SignalFrame: A pd.DataFrame alias documenting the strategy signal contract.
- WeightFrame: A pd.DataFrame alias documenting the normalized weight output contract.

These are structural type aliases (not subclasses). Runtime enforcement is provided
by validate_signal_frame() in signal/validator.py.
"""

from __future__ import annotations

import pandas as pd

# SignalFrame: the typed signal contract produced by any strategy module.
#
# Schema contract:
#   index   : pd.DatetimeIndex — one row per trading date (UTC or tz-naive).
#   columns : str — ticker symbols (e.g. "AAPL", "MSFT"), all non-empty strings.
#   values  : float — unconstrained signal scores (e.g. z-scores, ranks, raw scores).
#              NaN is allowed for tickers with no signal on a given date.
#              All-NaN columns trigger a warning from validate_signal_frame().
#
# Invariants enforced by validate_signal_frame():
#   1. index must be DatetimeIndex.
#   2. At least one column must be present.
#   3. All column names must be non-empty strings.
#
# Produced by: strategy modules (e.g. AI Washing Detector adapter).
# Consumed by: signal/adapter.py (normalization + position sizing).
SignalFrame = pd.DataFrame

# WeightFrame: the normalized position weight output after adapter processing.
#
# Schema contract:
#   index   : pd.DatetimeIndex — aligned to the input SignalFrame index.
#   columns : str — same ticker symbols as the input SignalFrame.
#   values  : float in [-1.0, +1.0] — portfolio weights after normalization.
#              Negative weights represent short positions.
#              The first row is always NaN (result of the look-ahead-prevention shift).
#
# Invariants:
#   - Row sums satisfy |sum(weights)| <= gross_exposure_limit (from SignalAdapterConfig).
#   - Produced after shifted(1) to prevent look-ahead bias.
#   - NaN rows must be masked before passing to the vectorbt engine.
#
# Produced by: signal/adapter.py.
# Consumed by: backtest engine (Phase 4).
WeightFrame = pd.DataFrame
