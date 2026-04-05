"""Kalshi API ingestion layer — clients, fetchers, Pydantic types, pipeline, and validator.

Note: IngestionPipeline and DataValidator are NOT imported at package init time to
avoid a circular import (ingestion.pipeline depends on db.repository which depends on
ingestion.types which is part of this package). Import them directly:

    from kalshi_backtest.ingestion.pipeline import IngestionPipeline, IngestionResult
    from kalshi_backtest.ingestion.validator import DataValidator, GapRecord, ValidationReport
"""
from kalshi_backtest.ingestion.client import (
    KalshiClientRouter,
    KalshiHistoricalClient,
    KalshiLiveClient,
)
from kalshi_backtest.ingestion.cutoff import CutoffResult, HistoricalCutoffResolver
from kalshi_backtest.ingestion.fetcher import CandlestickFetcher, MarketFetcher
from kalshi_backtest.ingestion.types import CandlestickRecord, MarketRecord

__all__ = [
    "CandlestickFetcher",
    "CandlestickRecord",
    "CutoffResult",
    "DataValidator",
    "GapRecord",
    "HistoricalCutoffResolver",
    "IngestionPipeline",
    "IngestionResult",
    "KalshiClientRouter",
    "KalshiHistoricalClient",
    "KalshiLiveClient",
    "MarketFetcher",
    "MarketRecord",
    "ValidationReport",
]
