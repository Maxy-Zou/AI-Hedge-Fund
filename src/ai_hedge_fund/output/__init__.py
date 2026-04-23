"""Phase-8 output subsystem: final signal assembly + portfolio view + formatters.

Public API (Plans 08-03 / 08-04 consume these as black-box contracts):
    assemble_final_signal:     pure-Python state -> FinalSignalOutput.
    derive_risk_score:         deterministic RiskAssessment -> int in [0, 100].
    format_signal_md:          FinalSignalOutput dict -> compact markdown.
    format_review_request_md:  review packet dict -> reviewer-facing markdown.
    query_portfolio_view:      episodic_memory -> sector-keyed ranked view
                               (SIG-02; fresh-by-construction, no cache).
"""

from __future__ import annotations

from ai_hedge_fund.output.formatter import format_review_request_md, format_signal_md
from ai_hedge_fund.output.portfolio_view import query_portfolio_view
from ai_hedge_fund.output.signal import assemble_final_signal, derive_risk_score

__all__ = [
    "assemble_final_signal",
    "derive_risk_score",
    "format_review_request_md",
    "format_signal_md",
    "query_portfolio_view",
]
