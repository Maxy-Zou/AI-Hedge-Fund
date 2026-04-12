"""Tests for SQLAlchemy data models.

Validates that all six data source models have the correct columns,
types, constraints, and inherit from the proper mixins.
"""

from __future__ import annotations

from sqlalchemy import inspect as sa_inspect

from ai_hedge_fund.db.base import Base, DualTimestampMixin
from ai_hedge_fund.db.models import (
    DailyPrice,
    InsiderTrade,
    MacroIndicator,
    NewsArticle,
    SecFiling,
    XbrlFact,
)


def _get_column_names(model: type) -> set[str]:
    """Get column names from a SQLAlchemy model class."""
    mapper = sa_inspect(model)
    return {col.key for col in mapper.columns}


def _get_unique_constraints(model: type) -> list[tuple[str, ...]]:
    """Get unique constraint column sets from a SQLAlchemy model class."""
    table = model.__table__
    constraints = []
    for constraint in table.constraints:
        if hasattr(constraint, "columns") and constraint.__class__.__name__ == "UniqueConstraint":
            constraints.append(tuple(col.name for col in constraint.columns))
    return constraints


class TestSecFiling:
    """Tests for SecFiling model."""

    def test_has_required_columns(self) -> None:
        expected = {
            "id",
            "ticker",
            "accession_no",
            "form_type",
            "filing_date",
            "sections_json",
            "summary_text",
            "as_of_date",
            "observed_date",
        }
        actual = _get_column_names(SecFiling)
        assert expected.issubset(actual), f"Missing columns: {expected - actual}"

    def test_unique_constraint_on_ticker_accession(self) -> None:
        constraints = _get_unique_constraints(SecFiling)
        assert ("ticker", "accession_no") in constraints

    def test_inherits_from_base(self) -> None:
        assert issubclass(SecFiling, Base)

    def test_uses_dual_timestamp_mixin(self) -> None:
        assert issubclass(SecFiling, DualTimestampMixin)


class TestXbrlFact:
    """Tests for XbrlFact model."""

    def test_has_required_columns(self) -> None:
        expected = {
            "id",
            "ticker",
            "cik",
            "concept",
            "value_cents",
            "unit",
            "fiscal_period",
            "fiscal_year",
            "filed_date",
            "as_of_date",
            "observed_date",
        }
        actual = _get_column_names(XbrlFact)
        assert expected.issubset(actual), f"Missing columns: {expected - actual}"

    def test_unique_constraint(self) -> None:
        constraints = _get_unique_constraints(XbrlFact)
        assert ("ticker", "concept", "fiscal_period", "fiscal_year") in constraints

    def test_inherits_from_base(self) -> None:
        assert issubclass(XbrlFact, Base)

    def test_uses_dual_timestamp_mixin(self) -> None:
        assert issubclass(XbrlFact, DualTimestampMixin)


class TestDailyPrice:
    """Tests for DailyPrice model."""

    def test_has_required_columns(self) -> None:
        expected = {
            "id",
            "ticker",
            "trade_date",
            "open_cents",
            "high_cents",
            "low_cents",
            "close_cents",
            "adj_close_cents",
            "volume",
            "source",
            "as_of_date",
            "observed_date",
        }
        actual = _get_column_names(DailyPrice)
        assert expected.issubset(actual), f"Missing columns: {expected - actual}"

    def test_unique_constraint(self) -> None:
        constraints = _get_unique_constraints(DailyPrice)
        assert ("ticker", "trade_date", "source") in constraints

    def test_inherits_from_base(self) -> None:
        assert issubclass(DailyPrice, Base)

    def test_uses_dual_timestamp_mixin(self) -> None:
        assert issubclass(DailyPrice, DualTimestampMixin)


class TestInsiderTrade:
    """Tests for InsiderTrade model."""

    def test_has_required_columns(self) -> None:
        expected = {
            "id",
            "ticker",
            "insider_name",
            "insider_title",
            "trade_type",
            "shares",
            "price_cents",
            "value_cents",
            "trade_date",
            "filing_date",
            "as_of_date",
            "observed_date",
        }
        actual = _get_column_names(InsiderTrade)
        assert expected.issubset(actual), f"Missing columns: {expected - actual}"

    def test_unique_constraint(self) -> None:
        constraints = _get_unique_constraints(InsiderTrade)
        assert (
            "ticker",
            "insider_name",
            "trade_date",
            "trade_type",
            "shares",
        ) in constraints

    def test_inherits_from_base(self) -> None:
        assert issubclass(InsiderTrade, Base)

    def test_uses_dual_timestamp_mixin(self) -> None:
        assert issubclass(InsiderTrade, DualTimestampMixin)


class TestNewsArticle:
    """Tests for NewsArticle model."""

    def test_has_required_columns(self) -> None:
        expected = {
            "id",
            "ticker",
            "headline",
            "source",
            "url",
            "sentiment_score",
            "published_date",
            "as_of_date",
            "observed_date",
        }
        actual = _get_column_names(NewsArticle)
        assert expected.issubset(actual), f"Missing columns: {expected - actual}"

    def test_unique_constraint(self) -> None:
        constraints = _get_unique_constraints(NewsArticle)
        assert ("ticker", "url") in constraints

    def test_inherits_from_base(self) -> None:
        assert issubclass(NewsArticle, Base)

    def test_uses_dual_timestamp_mixin(self) -> None:
        assert issubclass(NewsArticle, DualTimestampMixin)


class TestMacroIndicator:
    """Tests for MacroIndicator model."""

    def test_has_required_columns(self) -> None:
        expected = {
            "id",
            "series_id",
            "series_name",
            "value",
            "observation_date",
            "as_of_date",
            "observed_date",
        }
        actual = _get_column_names(MacroIndicator)
        assert expected.issubset(actual), f"Missing columns: {expected - actual}"

    def test_unique_constraint(self) -> None:
        constraints = _get_unique_constraints(MacroIndicator)
        assert ("series_id", "observation_date") in constraints

    def test_inherits_from_base(self) -> None:
        assert issubclass(MacroIndicator, Base)

    def test_uses_dual_timestamp_mixin(self) -> None:
        assert issubclass(MacroIndicator, DualTimestampMixin)


class TestModelTableCreation:
    """Tests that models can create tables in an in-memory database."""

    def test_create_all_tables(self, db_session) -> None:
        """Verify all 6 tables can be created via Base.metadata.create_all."""
        engine = db_session.get_bind()
        inspector = sa_inspect(engine)
        table_names = inspector.get_table_names()

        expected_tables = {
            "sec_filings",
            "xbrl_facts",
            "daily_prices",
            "insider_trades",
            "news_articles",
            "macro_indicators",
        }
        assert expected_tables.issubset(set(table_names)), (
            f"Missing tables: {expected_tables - set(table_names)}"
        )
