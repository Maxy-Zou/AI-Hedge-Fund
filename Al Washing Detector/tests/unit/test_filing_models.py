"""Unit tests for Filing and XBRLFact ORM models.

Tests inspect ORM metadata (columns, indexes, table names, types) without
requiring a database connection. Follows the same pattern as test_models.py.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Date, DateTime, String, inspect
from sqlalchemy.dialects.postgresql import JSONB


# ---------------------------------------------------------------------------
# Filing model tests
# ---------------------------------------------------------------------------


class TestFilingModel:
    """Tests for Filing ORM model."""

    def test_tablename(self):
        """Filing model has __tablename__ == 'sec_filings'."""
        from ai_washer.db.models import Filing

        assert Filing.__tablename__ == "sec_filings"

    def test_inherits_append_only_mixin(self):
        """Filing model inherits AppendOnlyMixin (has id, as_of_date, observed_date, created_at)."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        assert "id" in mapper.columns
        assert "as_of_date" in mapper.columns
        assert "observed_date" in mapper.columns
        assert "created_at" in mapper.columns

    def test_id_is_uuid_primary_key(self):
        """Filing.id is a UUID primary key from AppendOnlyMixin."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        col = mapper.columns["id"]
        assert col.primary_key is True

    def test_company_id_foreign_key(self):
        """Filing.company_id is FK to companies.id, not nullable."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        col = mapper.columns["company_id"]
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "companies.id" in fk_targets
        assert col.nullable is False

    def test_form_type_column(self):
        """Filing.form_type is String(10), not nullable."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        col = mapper.columns["form_type"]
        assert isinstance(col.type, String)
        assert col.type.length == 10
        assert col.nullable is False

    def test_accession_no_column(self):
        """Filing.accession_no is String(25), not nullable."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        col = mapper.columns["accession_no"]
        assert isinstance(col.type, String)
        assert col.type.length == 25
        assert col.nullable is False

    def test_filing_date_column(self):
        """Filing.filing_date is Date, not nullable."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        col = mapper.columns["filing_date"]
        assert isinstance(col.type, Date)
        assert col.nullable is False

    def test_period_of_report_nullable(self):
        """Filing.period_of_report is Date, nullable."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        col = mapper.columns["period_of_report"]
        assert isinstance(col.type, Date)
        assert col.nullable is True

    def test_sections_jsonb(self):
        """Filing.sections is JSONB, not nullable."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        col = mapper.columns["sections"]
        assert isinstance(col.type, JSONB)
        assert col.nullable is False

    def test_content_hash_nullable(self):
        """Filing.content_hash is String(64), nullable."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        col = mapper.columns["content_hash"]
        assert isinstance(col.type, String)
        assert col.type.length == 64
        assert col.nullable is True

    def test_collection_metadata_jsonb(self):
        """Filing.collection_metadata is JSONB, not nullable."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        col = mapper.columns["collection_metadata"]
        assert isinstance(col.type, JSONB)
        assert col.nullable is False

    def test_unique_index_company_form_accession(self):
        """Filing has unique index on (company_id, form_type, accession_no)."""
        from ai_washer.db.models import Filing

        table = Filing.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "uq_sec_filings_company_form_accession" in index_names
        # Verify it's unique
        for idx in table.indexes:
            if idx.name == "uq_sec_filings_company_form_accession":
                assert idx.unique is True

    def test_index_company_form_observed(self):
        """Filing has index on (company_id, form_type, observed_date)."""
        from ai_washer.db.models import Filing

        table = Filing.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_sec_filings_company_form_observed" in index_names

    def test_created_at_timestamp_with_timezone(self):
        """Filing.created_at is DateTime with timezone (from AppendOnlyMixin)."""
        from ai_washer.db.models import Filing

        mapper = inspect(Filing)
        col = mapper.columns["created_at"]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True

    def test_no_update_method(self):
        """Filing is append-only: no update method."""
        from ai_washer.db.models import Filing

        assert not hasattr(Filing, "update")

    def test_no_delete_method(self):
        """Filing is append-only: no delete method."""
        from ai_washer.db.models import Filing

        assert not hasattr(Filing, "delete")


# ---------------------------------------------------------------------------
# XBRLFact model tests
# ---------------------------------------------------------------------------


class TestXBRLFactModel:
    """Tests for XBRLFact ORM model."""

    def test_tablename(self):
        """XBRLFact model has __tablename__ == 'xbrl_facts'."""
        from ai_washer.db.models import XBRLFact

        assert XBRLFact.__tablename__ == "xbrl_facts"

    def test_inherits_append_only_mixin(self):
        """XBRLFact model inherits AppendOnlyMixin."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        assert "id" in mapper.columns
        assert "as_of_date" in mapper.columns
        assert "observed_date" in mapper.columns
        assert "created_at" in mapper.columns

    def test_id_is_uuid_primary_key(self):
        """XBRLFact.id is a UUID primary key from AppendOnlyMixin."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["id"]
        assert col.primary_key is True

    def test_company_id_foreign_key(self):
        """XBRLFact.company_id is FK to companies.id, not nullable."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["company_id"]
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "companies.id" in fk_targets
        assert col.nullable is False

    def test_concept_column(self):
        """XBRLFact.concept is String(50), not nullable."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["concept"]
        assert isinstance(col.type, String)
        assert col.type.length == 50
        assert col.nullable is False

    def test_tag_column(self):
        """XBRLFact.tag is String(100), not nullable."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["tag"]
        assert isinstance(col.type, String)
        assert col.type.length == 100
        assert col.nullable is False

    def test_value_cents_biginteger(self):
        """XBRLFact.value_cents is BigInteger per D-09, not nullable."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["value_cents"]
        assert isinstance(col.type, BigInteger)
        assert col.nullable is False

    def test_fiscal_year_column(self):
        """XBRLFact.fiscal_year is integer, not nullable."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["fiscal_year"]
        assert col.nullable is False

    def test_fiscal_period_column(self):
        """XBRLFact.fiscal_period is String(5), not nullable."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["fiscal_period"]
        assert isinstance(col.type, String)
        assert col.type.length == 5
        assert col.nullable is False

    def test_form_type_column(self):
        """XBRLFact.form_type is String(10), not nullable."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["form_type"]
        assert isinstance(col.type, String)
        assert col.type.length == 10
        assert col.nullable is False

    def test_filed_date_column(self):
        """XBRLFact.filed_date is Date, not nullable."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["filed_date"]
        assert isinstance(col.type, Date)
        assert col.nullable is False

    def test_end_date_column(self):
        """XBRLFact.end_date is Date, not nullable."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["end_date"]
        assert isinstance(col.type, Date)
        assert col.nullable is False

    def test_accession_no_column(self):
        """XBRLFact.accession_no is String(25), not nullable."""
        from ai_washer.db.models import XBRLFact

        mapper = inspect(XBRLFact)
        col = mapper.columns["accession_no"]
        assert isinstance(col.type, String)
        assert col.type.length == 25
        assert col.nullable is False

    def test_index_company_concept_end(self):
        """XBRLFact has index on (company_id, concept, end_date)."""
        from ai_washer.db.models import XBRLFact

        table = XBRLFact.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_xbrl_facts_company_concept_end" in index_names

    def test_unique_index_company_concept_end_fp(self):
        """XBRLFact has unique index on (company_id, concept, end_date, fiscal_period)."""
        from ai_washer.db.models import XBRLFact

        table = XBRLFact.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "uq_xbrl_facts_company_concept_end_fp" in index_names
        # Verify it's unique
        for idx in table.indexes:
            if idx.name == "uq_xbrl_facts_company_concept_end_fp":
                assert idx.unique is True

    def test_no_update_method(self):
        """XBRLFact is append-only: no update method."""
        from ai_washer.db.models import XBRLFact

        assert not hasattr(XBRLFact, "update")

    def test_no_delete_method(self):
        """XBRLFact is append-only: no delete method."""
        from ai_washer.db.models import XBRLFact

        assert not hasattr(XBRLFact, "delete")


# ---------------------------------------------------------------------------
# Migration 003 tests
# ---------------------------------------------------------------------------


class TestMigration003:
    """Tests for Alembic migration 003 structure."""

    def test_migration_file_exists(self):
        """Migration 003 file exists."""
        from pathlib import Path

        path = Path("src/ai_washer/db/migrations/versions/003_add_filing_tables.py")
        assert path.exists()

    def test_down_revision_is_002(self):
        """Migration 003 chains from migration 002."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migration_003",
            "src/ai_washer/db/migrations/versions/003_add_filing_tables.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.down_revision == "002_add_active"

    def test_has_upgrade_function(self):
        """Migration 003 has an upgrade function."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migration_003",
            "src/ai_washer/db/migrations/versions/003_add_filing_tables.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(getattr(mod, "upgrade", None))

    def test_has_downgrade_function(self):
        """Migration 003 has a downgrade function."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migration_003",
            "src/ai_washer/db/migrations/versions/003_add_filing_tables.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(getattr(mod, "downgrade", None))

    def test_revision_id(self):
        """Migration 003 has correct revision ID."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migration_003",
            "src/ai_washer/db/migrations/versions/003_add_filing_tables.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "003_add_filings"
