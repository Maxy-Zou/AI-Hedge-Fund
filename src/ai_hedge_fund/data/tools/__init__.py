"""Agent-callable data tool functions.

All tool functions enforce as_of_date via the @enforce_as_of_date decorator
to prevent look-ahead bias in agent data retrieval.
"""

from __future__ import annotations

from ai_hedge_fund.data.tools.filing_tools import get_filing_sections
from ai_hedge_fund.data.tools.financial_tools import get_financial_summary
from ai_hedge_fund.data.tools.insider_tools import get_insider_clusters
from ai_hedge_fund.data.tools.macro_tools import get_macro_context
from ai_hedge_fund.data.tools.price_tools import get_price_history
from ai_hedge_fund.data.tools.sentiment_tools import get_news_sentiment

__all__ = [
    "get_filing_sections",
    "get_financial_summary",
    "get_insider_clusters",
    "get_macro_context",
    "get_price_history",
    "get_news_sentiment",
]
