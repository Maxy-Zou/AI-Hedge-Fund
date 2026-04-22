"""SQLAlchemy models for data ingestion tables.

Six models covering all data sources: SEC filings, XBRL facts, daily prices,
insider trades, news articles, and macro indicators. All models use
DualTimestampMixin for temporal tracking (as_of_date / observed_date).
Monetary values are stored as BigInteger cents to avoid floating-point errors.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB as _JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ai_hedge_fund.db.base import Base, DualTimestampMixin


class SecFiling(Base, DualTimestampMixin):
    """SEC filing record (10-K, 10-Q, 8-K).

    Stores filing metadata, section-level text as JSON, and an optional
    natural language summary for LLM consumption.
    """

    __tablename__ = "sec_filings"
    __table_args__ = (
        UniqueConstraint("ticker", "accession_no", name="uq_sec_filings_ticker_accession"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    accession_no: Mapped[str] = mapped_column(String(30), nullable=False)
    form_type: Mapped[str] = mapped_column(String(10), nullable=False)
    filing_date: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)
    sections_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class XbrlFact(Base, DualTimestampMixin):
    """XBRL financial fact from CompanyFacts API.

    Stores individual financial concepts (revenue, net income, etc.) with
    their values in cents and fiscal period context.
    """

    __tablename__ = "xbrl_facts"
    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "concept",
            "fiscal_period",
            "fiscal_year",
            name="uq_xbrl_facts_ticker_concept_period_year",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    cik: Mapped[str] = mapped_column(String(10), nullable=False)
    concept: Mapped[str] = mapped_column(String(100), nullable=False)
    value_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String(10), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    filed_date: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)


class DailyPrice(Base, DualTimestampMixin):
    """Daily OHLCV price data cached from yfinance or Tiingo.

    All prices stored as cents (BigInteger) to avoid floating-point errors.
    The source field tracks data provenance for fallback handling.
    """

    __tablename__ = "daily_prices"
    __table_args__ = (
        UniqueConstraint(
            "ticker", "trade_date", "source", name="uq_daily_prices_ticker_date_source"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    trade_date: Mapped[str] = mapped_column(Date, nullable=False)
    open_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    high_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    low_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    close_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    adj_close_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="yfinance")


class InsiderTrade(Base, DualTimestampMixin):
    """SEC Form 4 insider trade record.

    Tracks individual insider transactions with price and value in cents.
    The unique constraint prevents duplicate ingestion of the same trade.
    """

    __tablename__ = "insider_trades"
    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "insider_name",
            "trade_date",
            "trade_type",
            "shares",
            name="uq_insider_trades_dedup",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    insider_name: Mapped[str] = mapped_column(String(200), nullable=False)
    insider_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trade_type: Mapped[str] = mapped_column(String(20), nullable=False)
    shares: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    value_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    trade_date: Mapped[str] = mapped_column(Date, nullable=False)
    filing_date: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)


class NewsArticle(Base, DualTimestampMixin):
    """News article with sentiment score from Finnhub.

    Stores article metadata and sentiment for daily digest generation.
    """

    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("ticker", "url", name="uq_news_articles_ticker_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    published_date: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)


class MacroIndicator(Base, DualTimestampMixin):
    """FRED macro indicator observation.

    Stores individual observations from FRED time series (rates, CPI, GDP, etc.).
    """

    __tablename__ = "macro_indicators"
    __table_args__ = (
        UniqueConstraint("series_id", "observation_date", name="uq_macro_indicators_series_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    series_name: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    observation_date: Mapped[str] = mapped_column(Date, nullable=False)


class PortfolioPosition(Base, DualTimestampMixin):
    """Paper-portfolio position snapshot for risk checks (Phase 6 RISK-03).

    Append-only per CLAUDE.md financial-time-series convention: closing or
    resizing a position writes a NEW row with a new ``as_of_date``; the
    ``(ticker, as_of_date)`` UniqueConstraint prevents duplicate snapshots
    within the same business date. ``sector`` is user-supplied on insert
    (A3 in 06-RESEARCH.md) -- no external lookup needed for v1.
    """

    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint("ticker", "as_of_date", name="uq_portfolio_positions_ticker_asof"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    sector: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_value_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(20), nullable=False, default="equity")


class EpisodicMemory(Base, DualTimestampMixin):
    """Append-only episodic record of a completed analysis or trade outcome.

    Two record types share this table:
        record_type='analysis'  -- produced by episodic_store_node (Plan 07-03)
        record_type='outcome'   -- produced by scripts/ingest_outcome.py (Plan 07-04)

    Append-only by DESIGN: duplicates are allowed (multiple analyses of the
    same ticker on the same day). Contrast with PortfolioPosition which
    UniqueConstraint-guards (ticker, as_of_date) -- episodic memory
    deliberately lifts that guard because duplicate analyses are a valid
    operational signal, not an error.

    Retention: 90 days from as_of_date, enforced by
    ``src/ai_hedge_fund/scripts/purge_expired_episodic.py``.
    """

    __tablename__ = "episodic_memory"
    __table_args__ = (
        Index("ix_episodic_ticker_asof", "ticker", "as_of_date"),
        Index("ix_episodic_sector_asof", "sector", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    sector: Mapped[str] = mapped_column(String(50), nullable=False, default="Unknown")
    record_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "analysis" | "outcome"

    # Hot-path filter fields for B-tree indexing (rationale: 07-RESEARCH.md §Pattern 1)
    signal_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    linked_analysis_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Phase-6 link-back audit key (policy version that produced the decision)
    policy_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Full thesis + signal + risk_assessment snapshot.
    # Uses JSONB on PostgreSQL (indexable via GIN) with a SQLite-JSON
    # fallback for the in-memory test DB; the .with_variant() call binds
    # both dialects. Nullable=False to prevent half-written audit rows.
    payload: Mapped[dict] = mapped_column(_JSONB().with_variant(JSON, "sqlite"), nullable=False)
