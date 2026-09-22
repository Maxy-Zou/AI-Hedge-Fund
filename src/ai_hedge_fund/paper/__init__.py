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
    SeedFormatError,
    SignalNotFound,
    SignalTickerMismatch,
    SignalWrongRecordType,
    TradeNotFound,
)
from ai_hedge_fund.paper.recall import query_paper_fills, query_paper_trades
from ai_hedge_fund.paper.records import (
    NewPaperFill,
    NewPaperTrade,
    PaperFillRecord,
    PaperTradeRecord,
)
from ai_hedge_fund.paper.seed import (
    resolve_signal_id,
    seed_paper_fills_from_csv,
    seed_paper_trades_from_csv,
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
    "SeedFormatError",
    "SignalNotFound",
    "SignalTickerMismatch",
    "SignalWrongRecordType",
    "TradeNotFound",
    "insert_paper_fill",
    "insert_paper_trade",
    "query_paper_fills",
    "query_paper_trades",
    "resolve_signal_id",
    "seed_paper_fills_from_csv",
    "seed_paper_trades_from_csv",
]
