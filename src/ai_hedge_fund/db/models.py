"""SQLAlchemy models for data ingestion tables.

Data-source models (SEC filings, XBRL facts, daily prices, insider trades,
news articles, macro indicators), the Phase-6 portfolio snapshot, the Phase-7
episodic memory, the Phase-9 paper-trading ledger (paper_trades,
paper_fills), and the Phase-11 mark-to-market tables (paper_cash_events,
paper_pnl_daily). All models use DualTimestampMixin for temporal tracking
(as_of_date / observed_date). Monetary values are stored as BigInteger cents
to avoid floating-point errors.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB as _JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ai_hedge_fund.db.append_only import AppendOnlyGuard, attach_postgres_guard
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


class PaperTrade(Base, DualTimestampMixin, AppendOnlyGuard):
    """One order *intent* and its synchronous broker response (Phase 9, PT-01/03).

    Append-only: a row is written once at submission time and never updated.
    A broker rejection is recoverable by inserting a new row with
    ``attempt_no + 1`` -- the ``(signal_id, attempt_no)`` UniqueConstraint is
    the idempotency grain (a network retry of the same attempt is deduplicated
    at the DB; a deliberate retry is a new immutable row). ``signal_id``
    foreign-keys to the ``episodic_memory`` analysis row the order executes,
    so every trade traces back to its thesis. ``ticker`` is denormalized
    from that row for join-free recall and validated on insert
    (:mod:`ai_hedge_fund.paper.store`).

    The two paired CHECKs encode structural facts, not policy: a limit
    price exists iff the order is a limit order; a broker order id exists
    iff the broker accepted. ``risk_status_at_submit`` is an audit snapshot
    of the risk verdict at submit time; the circuit breaker that acts on it
    lives in Phase 10.
    """

    __tablename__ = "paper_trades"
    __table_args__ = (
        UniqueConstraint("signal_id", "attempt_no", name="uq_paper_trades_signal_attempt"),
        UniqueConstraint("broker_order_id", name="uq_paper_trades_broker_order_id"),
        CheckConstraint("attempt_no >= 1", name="ck_paper_trades_attempt_no"),
        CheckConstraint("quantity >= 0", name="ck_paper_trades_quantity"),
        CheckConstraint(
            "submit_status <> 'submitted' OR quantity > 0",
            name="ck_paper_trades_submitted_qty",
        ),
        CheckConstraint("side IN ('buy', 'sell')", name="ck_paper_trades_side"),
        CheckConstraint("order_type IN ('market', 'limit')", name="ck_paper_trades_order_type"),
        CheckConstraint(
            "submit_status IN ('submitted', 'rejected', 'refused_veto', "
            "'refused_review', 'refused_policy')",
            name="ck_paper_trades_submit_status",
        ),
        CheckConstraint(
            "(order_type = 'limit') = (limit_price_cents IS NOT NULL)",
            name="ck_paper_trades_limit_price",
        ),
        CheckConstraint(
            "(submit_status = 'submitted') = (broker_order_id IS NOT NULL)",
            name="ck_paper_trades_broker_id",
        ),
        Index("ix_paper_trades_ticker_asof", "ticker", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("episodic_memory.id"), nullable=False, index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # "buy" | "sell"
    order_type: Mapped[str] = mapped_column(String(6), nullable=False)  # "market" | "limit"
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)  # whole shares (D3)
    limit_price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    submit_status: Mapped[str] = mapped_column(String(20), nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_status_at_submit: Mapped[str] = mapped_column(String(10), nullable=False)
    policy_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    review_policy_sha: Mapped[str] = mapped_column(String(64), nullable=False)

    # Full FinalSignalOutput snapshot + broker request/response. none_as_null
    # makes a Python None a SQL NULL (rejected by NOT NULL) instead of the JSON
    # string 'null', which SQLAlchemy's JSON type would otherwise store silently.
    payload: Mapped[dict] = mapped_column(
        _JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite"),
        nullable=False,
    )


class PaperFill(Base, DualTimestampMixin, AppendOnlyGuard):
    """One fill event reported by the broker for a :class:`PaperTrade` (Phase 9, PT-02).

    Append-only. A partially-filled order produces several rows.
    ``broker_fill_id`` is unique so repeated polling of the broker cannot
    double-record the same fill. ``as_of_date`` is the trade date of the
    fill; ``filled_at`` is the broker's own timestamp.
    """

    __tablename__ = "paper_fills"
    __table_args__ = (
        UniqueConstraint("broker_fill_id", name="uq_paper_fills_broker_fill_id"),
        CheckConstraint("filled_qty > 0", name="ck_paper_fills_filled_qty"),
        CheckConstraint("fill_price_cents > 0", name="ck_paper_fills_fill_price"),
        Index("ix_paper_fills_asof", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("paper_trades.id"), nullable=False, index=True)
    broker_fill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    filled_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    fill_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    filled_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(
        _JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite"),
        nullable=False,
    )


# Alpaca non-trade activity types kept by Phase 11 (11-SPEC A1): dividend cash
# (incl. withholding) and the corporate actions the EOD job must detect.
CASH_ACTIVITY_TYPES = (
    "DIV", "DIVCGL", "DIVCGS", "DIVNRA", "DIVROC", "DIVTXEX", "DIVWH",
    "SPLIT", "SPIN", "MA", "NC",
)  # fmt: skip
_CASH_TYPES_SQL = ", ".join(f"'{t}'" for t in CASH_ACTIVITY_TYPES)


class PaperCashEvent(Base, DualTimestampMixin, AppendOnlyGuard):
    """One broker non-trade activity: dividend cash or a corporate action (Phase 11, A1).

    Append-only. ``broker_activity_id`` is unique so repeated polling cannot
    double-record an event. ``net_amount_cents`` is signed (``DIVWH``
    withholding is negative) and 0 for non-cash actions (``SPLIT`` etc.).
    Stored for every ticker the broker reports; the EOD job filters.
    """

    __tablename__ = "paper_cash_events"
    __table_args__ = (
        UniqueConstraint("broker_activity_id", name="uq_paper_cash_events_activity"),
        CheckConstraint(
            f"activity_type IN ({_CASH_TYPES_SQL})", name="ck_paper_cash_events_activity_type"
        ),
        Index("ix_paper_cash_events_ticker_date", "ticker", "event_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    broker_activity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(8), nullable=False)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    event_date: Mapped[str] = mapped_column(Date, nullable=False)
    net_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict] = mapped_column(
        _JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite"),
        nullable=False,
    )


class PaperPnlDaily(Base, DualTimestampMixin, AppendOnlyGuard):
    """One signal's cumulative mark-to-market P&L at one trading day's close (Phase 11, MTM-02).

    Append-only, exactly one row per ``(signal_id, pnl_date)`` -- the EOD job
    skips pairs that exist and never updates (MTM-04). Values are cumulative
    since the signal's first fill, so a missing day never corrupts a later
    one; daily deltas are derived by the rollup. ``attribution`` holds the
    signal's frozen attribution labels; ``payload`` the input ids needed to
    reproduce the row.
    """

    __tablename__ = "paper_pnl_daily"
    __table_args__ = (
        UniqueConstraint("signal_id", "pnl_date", name="uq_paper_pnl_daily_signal_date"),
        CheckConstraint("open_qty >= 0", name="ck_paper_pnl_daily_open_qty"),
        CheckConstraint("open_cost_cents >= 0", name="ck_paper_pnl_daily_open_cost"),
        CheckConstraint("mark_close_cents > 0", name="ck_paper_pnl_daily_mark"),
        CheckConstraint(
            "total_pnl_cents = realized_pnl_cents + unrealized_pnl_cents",
            name="ck_paper_pnl_daily_total",
        ),
        Index("ix_paper_pnl_daily_date", "pnl_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("episodic_memory.id"), nullable=False)
    pnl_date: Mapped[str] = mapped_column(Date, nullable=False)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    open_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    open_cost_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mark_close_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_source: Mapped[str] = mapped_column(String(20), nullable=False)
    realized_pnl_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unrealized_pnl_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_pnl_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attribution: Mapped[dict] = mapped_column(
        _JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite"),
        nullable=False,
    )
    mtm_policy_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(
        _JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite"),
        nullable=False,
    )


# L3: PostgreSQL append-only trigger, produced by create_all as well as by migrations 004/007.
attach_postgres_guard(PaperTrade.__table__)
attach_postgres_guard(PaperFill.__table__)
attach_postgres_guard(PaperCashEvent.__table__)
attach_postgres_guard(PaperPnlDaily.__table__)
