"""Signal source loaders for the fund-backtest package.

Each loader reads from an external data source and converts the result
into a SignalFrame suitable for the SignalAdapter pipeline.

Available loaders:
- AiWashingLoader: reads AI Washing Risk Scores from the shared PostgreSQL database.
- SignalLoadError: raised by loaders when the data source is unavailable or empty.
"""
from __future__ import annotations

from fund_backtest.signal.loaders.ai_washing import AiWashingLoader, SignalLoadError

__all__ = ["AiWashingLoader", "SignalLoadError"]
