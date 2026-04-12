"""Create data ingestion tables.

Revision ID: 001
Revises:
Create Date: 2026-04-12

Creates tables for all six data sources:
- sec_filings: SEC 10-K, 10-Q, 8-K filings
- xbrl_facts: XBRL financial data from CompanyFacts API
- daily_prices: Equity OHLCV prices (yfinance/Tiingo)
- insider_trades: SEC Form 4 insider transactions
- news_articles: News with sentiment scores (Finnhub)
- macro_indicators: FRED macro data (rates, CPI, GDP)
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sec_filings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(10), nullable=False, index=True),
        sa.Column("accession_no", sa.String(30), nullable=False),
        sa.Column("form_type", sa.String(10), nullable=False),
        sa.Column("filing_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sections_json", sa.Text(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("as_of_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observed_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "ticker", "accession_no", name="uq_sec_filings_ticker_accession"
        ),
    )

    op.create_table(
        "xbrl_facts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(10), nullable=False, index=True),
        sa.Column("cik", sa.String(10), nullable=False),
        sa.Column("concept", sa.String(100), nullable=False),
        sa.Column("value_cents", sa.BigInteger(), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("fiscal_period", sa.String(10), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("filed_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observed_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "ticker",
            "concept",
            "fiscal_period",
            "fiscal_year",
            name="uq_xbrl_facts_ticker_concept_period_year",
        ),
    )

    op.create_table(
        "daily_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(10), nullable=False, index=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open_cents", sa.BigInteger(), nullable=False),
        sa.Column("high_cents", sa.BigInteger(), nullable=False),
        sa.Column("low_cents", sa.BigInteger(), nullable=False),
        sa.Column("close_cents", sa.BigInteger(), nullable=False),
        sa.Column("adj_close_cents", sa.BigInteger(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(20), server_default="yfinance"),
        sa.Column("as_of_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observed_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "ticker",
            "trade_date",
            "source",
            name="uq_daily_prices_ticker_date_source",
        ),
    )

    op.create_table(
        "insider_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(10), nullable=False, index=True),
        sa.Column("insider_name", sa.String(200), nullable=False),
        sa.Column("insider_title", sa.String(200), nullable=True),
        sa.Column("trade_type", sa.String(20), nullable=False),
        sa.Column("shares", sa.BigInteger(), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=True),
        sa.Column("value_cents", sa.BigInteger(), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("filing_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observed_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "ticker",
            "insider_name",
            "trade_date",
            "trade_type",
            "shares",
            name="uq_insider_trades_dedup",
        ),
    )

    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(10), nullable=False, index=True),
        sa.Column("headline", sa.String(500), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observed_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "ticker", "url", name="uq_news_articles_ticker_url"
        ),
    )

    op.create_table(
        "macro_indicators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.String(20), nullable=False, index=True),
        sa.Column("series_name", sa.String(200), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("as_of_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "observed_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "series_id",
            "observation_date",
            name="uq_macro_indicators_series_date",
        ),
    )


def downgrade() -> None:
    op.drop_table("macro_indicators")
    op.drop_table("news_articles")
    op.drop_table("insider_trades")
    op.drop_table("daily_prices")
    op.drop_table("xbrl_facts")
    op.drop_table("sec_filings")
