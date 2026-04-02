"""Tests for database base classes, mixins, and ORM models."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, Integer, SmallInteger, String, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# Task 1: Base class and mixin tests
# ---------------------------------------------------------------------------


class TestBase:
    """Tests for the DeclarativeBase subclass."""

    def test_base_is_declarative_base(self):
        from ai_washer.db.base import Base

        assert issubclass(Base, DeclarativeBase)


class TestDualTimestampMixin:
    """Tests for DualTimestampMixin columns."""

    def test_as_of_date_column_exists(self):
        from ai_washer.db.base import Base, DualTimestampMixin

        # Create a concrete model to test the mixin
        class _TestDual(DualTimestampMixin, Base):
            __tablename__ = "_test_dual_ts"
            id: int = pytest.importorskip("sqlalchemy").Column(Integer, primary_key=True)

        mapper = inspect(_TestDual)
        col = mapper.columns["as_of_date"]
        assert isinstance(col.type, Date)
        assert col.nullable is False

    def test_observed_date_column_exists(self):
        from ai_washer.db.base import Base, DualTimestampMixin

        class _TestDual2(DualTimestampMixin, Base):
            __tablename__ = "_test_dual_ts2"
            id: int = pytest.importorskip("sqlalchemy").Column(Integer, primary_key=True)

        mapper = inspect(_TestDual2)
        col = mapper.columns["observed_date"]
        assert isinstance(col.type, Date)
        assert col.nullable is False


class TestAppendOnlyMixin:
    """Tests for AppendOnlyMixin columns and UUID generation."""

    def test_id_is_uuid_primary_key(self):
        from ai_washer.db.base import AppendOnlyMixin, Base

        class _TestAppend(AppendOnlyMixin, Base):
            __tablename__ = "_test_append_only"

        mapper = inspect(_TestAppend)
        col = mapper.columns["id"]
        assert col.primary_key is True

    def test_created_at_column_exists(self):
        from ai_washer.db.base import AppendOnlyMixin, Base

        class _TestAppend2(AppendOnlyMixin, Base):
            __tablename__ = "_test_append_only2"

        mapper = inspect(_TestAppend2)
        col = mapper.columns["created_at"]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True
        assert col.nullable is False

    def test_inherits_dual_timestamps(self):
        from ai_washer.db.base import AppendOnlyMixin, Base

        class _TestAppend3(AppendOnlyMixin, Base):
            __tablename__ = "_test_append_only3"

        mapper = inspect(_TestAppend3)
        assert "as_of_date" in mapper.columns
        assert "observed_date" in mapper.columns

    def test_uuid_default_generation(self):
        from ai_washer.db.base import AppendOnlyMixin, Base

        class _TestAppend4(AppendOnlyMixin, Base):
            __tablename__ = "_test_append_only4"

        mapper = inspect(_TestAppend4)
        col = mapper.columns["id"]
        # The column should have a default callable that produces UUIDs
        assert col.default is not None
        assert col.default.is_callable is True
        # Invoke the default with the expected SQLAlchemy context signature
        generated = col.default.arg(None)
        assert isinstance(generated, uuid.UUID)


# ---------------------------------------------------------------------------
# Task 2: ORM model tests
# ---------------------------------------------------------------------------


class TestCompanyModel:
    """Tests for Company ORM model."""

    def test_tablename(self):
        from ai_washer.db.models import Company

        assert Company.__tablename__ == "companies"

    def test_id_is_uuid_primary_key(self):
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["id"]
        assert col.primary_key is True

    def test_ticker_column(self):
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["ticker"]
        assert isinstance(col.type, String)
        assert col.type.length == 10
        assert col.unique is True
        assert col.nullable is False

    def test_name_column(self):
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["name"]
        assert isinstance(col.type, String)
        assert col.type.length == 255
        assert col.nullable is False

    def test_cik_column_nullable(self):
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["cik"]
        assert isinstance(col.type, String)
        assert col.type.length == 10
        assert col.nullable is True

    def test_sector_column_nullable(self):
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["sector"]
        assert isinstance(col.type, String)
        assert col.type.length == 100
        assert col.nullable is True

    def test_market_cap_cents_biginteger(self):
        """Per D-09: all monetary values use BIGINT storage."""
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["market_cap_cents"]
        assert isinstance(col.type, BigInteger)
        assert col.nullable is True

    def test_aliases_jsonb(self):
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["aliases"]
        assert isinstance(col.type, JSONB)
        assert col.nullable is False

    def test_created_at_column(self):
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["created_at"]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True

    def test_updated_at_column(self):
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["updated_at"]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True


class TestDailyScoreModel:
    """Tests for DailyScore ORM model."""

    def test_tablename(self):
        from ai_washer.db.models import DailyScore

        assert DailyScore.__tablename__ == "daily_scores"

    def test_composite_primary_key(self):
        """PostgreSQL partitioning requires partition key in PK."""
        from ai_washer.db.models import DailyScore

        mapper = inspect(DailyScore)
        pk_cols = [col.name for col in mapper.primary_key]
        assert "id" in pk_cols
        assert "scored_at" in pk_cols

    def test_partition_by_range(self):
        """Per D-06: monthly range partitioning on scored_at."""
        from ai_washer.db.models import DailyScore

        table_args = DailyScore.__table_args__
        # table_args is a tuple; last element is the dict with postgresql_partition_by
        partition_dict = table_args[-1] if isinstance(table_args[-1], dict) else {}
        assert partition_dict.get("postgresql_partition_by") == "RANGE (scored_at)"

    def test_company_id_foreign_key(self):
        from ai_washer.db.models import DailyScore

        mapper = inspect(DailyScore)
        col = mapper.columns["company_id"]
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "companies.id" in fk_targets
        assert col.nullable is False

    def test_composite_score_smallinteger(self):
        from ai_washer.db.models import DailyScore

        mapper = inspect(DailyScore)
        col = mapper.columns["composite_score"]
        assert isinstance(col.type, SmallInteger)
        assert col.nullable is False

    def test_signal_breakdown_jsonb(self):
        from ai_washer.db.models import DailyScore

        mapper = inspect(DailyScore)
        col = mapper.columns["signal_breakdown"]
        assert isinstance(col.type, JSONB)
        assert col.nullable is False

    def test_confidence_float(self):
        from ai_washer.db.models import DailyScore

        mapper = inspect(DailyScore)
        col = mapper.columns["confidence"]
        assert isinstance(col.type, (Float, type(mapper.columns["confidence"].type)))
        assert col.nullable is False

    def test_weights_used_jsonb(self):
        from ai_washer.db.models import DailyScore

        mapper = inspect(DailyScore)
        col = mapper.columns["weights_used"]
        assert isinstance(col.type, JSONB)
        assert col.nullable is False

    def test_run_id_column(self):
        from ai_washer.db.models import DailyScore

        mapper = inspect(DailyScore)
        col = mapper.columns["run_id"]
        assert col.nullable is False

    def test_dual_timestamps_present(self):
        """Per D-08: dual timestamps on financial data tables."""
        from ai_washer.db.models import DailyScore

        mapper = inspect(DailyScore)
        assert "as_of_date" in mapper.columns
        assert "observed_date" in mapper.columns

    def test_scored_at_column(self):
        from ai_washer.db.models import DailyScore

        mapper = inspect(DailyScore)
        col = mapper.columns["scored_at"]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True

    def test_company_scored_index(self):
        from ai_washer.db.models import DailyScore

        table = DailyScore.__table__
        index_names = [idx.name for idx in table.indexes]
        assert "ix_daily_scores_company_scored" in index_names


class TestSignalDetailModel:
    """Tests for SignalDetail ORM model."""

    def test_tablename(self):
        from ai_washer.db.models import SignalDetail

        assert SignalDetail.__tablename__ == "signal_details"

    def test_id_is_uuid_primary_key(self):
        from ai_washer.db.models import SignalDetail

        mapper = inspect(SignalDetail)
        col = mapper.columns["id"]
        assert col.primary_key is True

    def test_company_id_foreign_key(self):
        from ai_washer.db.models import SignalDetail

        mapper = inspect(SignalDetail)
        col = mapper.columns["company_id"]
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "companies.id" in fk_targets
        assert col.nullable is False

    def test_signal_type_column(self):
        from ai_washer.db.models import SignalDetail

        mapper = inspect(SignalDetail)
        col = mapper.columns["signal_type"]
        assert isinstance(col.type, String)
        assert col.type.length == 50
        assert col.nullable is False

    def test_score_smallinteger(self):
        from ai_washer.db.models import SignalDetail

        mapper = inspect(SignalDetail)
        col = mapper.columns["score"]
        assert isinstance(col.type, SmallInteger)
        assert col.nullable is False

    def test_evidence_jsonb(self):
        """Per D-05: JSONB for flexible content."""
        from ai_washer.db.models import SignalDetail

        mapper = inspect(SignalDetail)
        col = mapper.columns["evidence"]
        assert isinstance(col.type, JSONB)
        assert col.nullable is False

    def test_run_id_column(self):
        from ai_washer.db.models import SignalDetail

        mapper = inspect(SignalDetail)
        col = mapper.columns["run_id"]
        assert col.nullable is False

    def test_dual_timestamps_present(self):
        """Per D-08: dual timestamps from AppendOnlyMixin."""
        from ai_washer.db.models import SignalDetail

        mapper = inspect(SignalDetail)
        assert "as_of_date" in mapper.columns
        assert "observed_date" in mapper.columns

    def test_created_at_present(self):
        from ai_washer.db.models import SignalDetail

        mapper = inspect(SignalDetail)
        assert "created_at" in mapper.columns

    def test_signal_detail_index(self):
        from ai_washer.db.models import SignalDetail

        table = SignalDetail.__table__
        index_names = [idx.name for idx in table.indexes]
        assert "ix_signal_details_company_type_date" in index_names

    def test_no_update_method(self):
        """Append-only: no mutation methods."""
        from ai_washer.db.models import SignalDetail

        assert not hasattr(SignalDetail, "update")

    def test_no_delete_method(self):
        """Append-only: no mutation methods."""
        from ai_washer.db.models import SignalDetail

        assert not hasattr(SignalDetail, "delete")


class TestPipelineRunModel:
    """Tests for PipelineRun ORM model."""

    def test_tablename(self):
        from ai_washer.db.models import PipelineRun

        assert PipelineRun.__tablename__ == "pipeline_runs"

    def test_id_is_uuid_primary_key(self):
        from ai_washer.db.models import PipelineRun

        mapper = inspect(PipelineRun)
        col = mapper.columns["id"]
        assert col.primary_key is True

    def test_started_at_column(self):
        from ai_washer.db.models import PipelineRun

        mapper = inspect(PipelineRun)
        col = mapper.columns["started_at"]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True
        assert col.nullable is False

    def test_ended_at_nullable(self):
        from ai_washer.db.models import PipelineRun

        mapper = inspect(PipelineRun)
        col = mapper.columns["ended_at"]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True
        assert col.nullable is True

    def test_status_column(self):
        from ai_washer.db.models import PipelineRun

        mapper = inspect(PipelineRun)
        col = mapper.columns["status"]
        assert isinstance(col.type, String)
        assert col.type.length == 20
        assert col.nullable is False

    def test_companies_processed_default(self):
        from ai_washer.db.models import PipelineRun

        mapper = inspect(PipelineRun)
        col = mapper.columns["companies_processed"]
        assert col.default is not None

    def test_errors_jsonb(self):
        from ai_washer.db.models import PipelineRun

        mapper = inspect(PipelineRun)
        col = mapper.columns["errors"]
        assert isinstance(col.type, JSONB)
        assert col.nullable is False

    def test_created_at_column(self):
        from ai_washer.db.models import PipelineRun

        mapper = inspect(PipelineRun)
        col = mapper.columns["created_at"]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True


class TestCompanyActiveFields:
    """Tests for Company is_active and deactivation_reason columns (Phase 2)."""

    def test_is_active_column_exists(self):
        """Company model has is_active column of type Boolean."""
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["is_active"]
        assert isinstance(col.type, Boolean)
        assert col.nullable is False

    def test_is_active_default_true(self):
        """New Company() defaults to is_active=True."""
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["is_active"]
        # server_default should contain 'true'
        assert col.server_default is not None
        server_default_text = str(col.server_default.arg)
        assert "true" in server_default_text.lower()

    def test_deactivation_reason_column_exists(self):
        """Company model has deactivation_reason column of type String(255), nullable."""
        from ai_washer.db.models import Company

        mapper = inspect(Company)
        col = mapper.columns["deactivation_reason"]
        assert isinstance(col.type, String)
        assert col.type.length == 255
        assert col.nullable is True

    def test_deactivated_company_valid(self):
        """Company with is_active=False and deactivation_reason='delisted' is valid."""
        from ai_washer.db.models import Company

        company = Company(
            ticker="TEST",
            name="Test Corp",
            is_active=False,
            deactivation_reason="delisted",
        )
        assert company.is_active is False
        assert company.deactivation_reason == "delisted"

    def test_new_company_defaults(self):
        """New Company() defaults to is_active=True and deactivation_reason=None."""
        from ai_washer.db.models import Company

        company = Company(ticker="DFLT", name="Default Corp")
        # is_active has a Python default via init (True); server_default handles DB side
        assert company.deactivation_reason is None


class TestNoMutationMethods:
    """Verify append-only models have no update/delete methods."""

    def test_daily_score_no_update(self):
        from ai_washer.db.models import DailyScore

        assert not hasattr(DailyScore, "update")

    def test_daily_score_no_delete(self):
        from ai_washer.db.models import DailyScore

        assert not hasattr(DailyScore, "delete")

    def test_signal_detail_no_update(self):
        from ai_washer.db.models import SignalDetail

        assert not hasattr(SignalDetail, "update")

    def test_signal_detail_no_delete(self):
        from ai_washer.db.models import SignalDetail

        assert not hasattr(SignalDetail, "delete")


# ---------------------------------------------------------------------------
# Task 2: Session factory tests
# ---------------------------------------------------------------------------


class TestSessionFactory:
    """Tests for engine creation and session factory."""

    def test_create_engine_from_settings_returns_engine(self):
        from sqlalchemy import Engine

        from ai_washer.config import AppSettings
        from ai_washer.db.session import create_engine_from_settings

        settings = AppSettings(
            database_url="postgresql+psycopg://localhost:5432/test_db",
            edgar_identity="test test@test.com",
        )
        engine = create_engine_from_settings(settings)
        assert isinstance(engine, Engine)

    def test_get_session_factory_returns_callable(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from ai_washer.db.session import get_session_factory

        engine = create_engine("sqlite:///:memory:")
        factory = get_session_factory(engine)
        assert callable(factory)
        assert isinstance(factory, sessionmaker)


# ---------------------------------------------------------------------------
# Task 2: Public API re-export tests
# ---------------------------------------------------------------------------


class TestDbPackageExports:
    """Tests for ai_washer.db public API."""

    def test_import_all_models(self):
        from ai_washer.db import Company, DailyScore, PipelineRun, SignalDetail

        assert Company.__tablename__ == "companies"
        assert DailyScore.__tablename__ == "daily_scores"
        assert SignalDetail.__tablename__ == "signal_details"
        assert PipelineRun.__tablename__ == "pipeline_runs"

    def test_import_base_classes(self):
        from ai_washer.db import AppendOnlyMixin, Base, DualTimestampMixin

        assert Base is not None
        assert DualTimestampMixin is not None
        assert AppendOnlyMixin is not None

    def test_import_session_factory(self):
        from ai_washer.db import create_engine_from_settings, get_session_factory

        assert callable(create_engine_from_settings)
        assert callable(get_session_factory)
