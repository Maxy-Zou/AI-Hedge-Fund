"""Agent-callable data tool functions.

Each tool enforces as_of_date for temporal correctness and returns
natural language summaries for LLM consumption.
"""

from __future__ import annotations

from ai_hedge_fund.data.tools.insider_tools import get_insider_clusters
from ai_hedge_fund.data.tools.price_tools import get_price_history

__all__ = [
    "get_insider_clusters",
    "get_price_history",
]
