"""Phase-8 output subsystem: final signal assembly + portfolio view + formatters.

Public API (Plans 08-03 / 08-04 consume these as black-box contracts):
    assemble_final_signal: pure-Python state -> FinalSignalOutput.
    derive_risk_score:     deterministic RiskAssessment -> int in [0, 100].

Additional re-exports land in later plans (format_signal_md,
format_review_request_md in Task 3 of this plan; portfolio_view helpers in
Plan 08-02).
"""

from __future__ import annotations

from ai_hedge_fund.output.signal import assemble_final_signal, derive_risk_score

__all__ = [
    "assemble_final_signal",
    "derive_risk_score",
]
