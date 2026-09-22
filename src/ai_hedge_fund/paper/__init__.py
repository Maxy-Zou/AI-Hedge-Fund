"""Paper-trading ledger: append-only storage for order intents and fills (Phase 9).

Layout mirrors :mod:`ai_hedge_fund.memory`: validated input + frozen read
models in ``records``, writers in ``store``, temporal recall in ``recall``,
CSV seeders (test fixtures) in ``seed``, typed errors in ``errors``.
"""

from ai_hedge_fund.paper.errors import (
    AmbiguousSignal,
    DuplicateFill,
    DuplicateSubmission,
    PaperStoreError,
    SignalNotFound,
    SignalTickerMismatch,
    SignalWrongRecordType,
    TradeNotFound,
)
from ai_hedge_fund.paper.records import (
    NewPaperFill,
    NewPaperTrade,
    PaperFillRecord,
    PaperTradeRecord,
)
from ai_hedge_fund.paper.store import insert_paper_fill, insert_paper_trade

__all__ = [
    "AmbiguousSignal",
    "DuplicateFill",
    "DuplicateSubmission",
    "NewPaperFill",
    "NewPaperTrade",
    "PaperFillRecord",
    "PaperStoreError",
    "PaperTradeRecord",
    "SignalNotFound",
    "SignalTickerMismatch",
    "SignalWrongRecordType",
    "TradeNotFound",
    "insert_paper_fill",
    "insert_paper_trade",
]
