"""Agent-callable data tool functions.

All tool functions enforce as_of_date via the @enforce_as_of_date decorator
to prevent look-ahead bias in agent data retrieval.
"""

from __future__ import annotations

from ai_hedge_fund.data.tools.filing_tools import get_filing_sections
from ai_hedge_fund.data.tools.financial_tools import get_financial_summary

__all__ = [
    "get_filing_sections",
    "get_financial_summary",
]
