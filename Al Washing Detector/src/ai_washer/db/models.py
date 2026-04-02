"""SQLAlchemy ORM models for the AI Washing Detector.

Eleven tables:
- companies: Entity table for tracked public companies
- daily_scores: Partitioned append-only composite AI washing scores
- signal_details: Append-only individual signal scores with evidence
- pipeline_runs: Operational tracking for batch runs
- sec_filings: Append-only SEC filing text and metadata (Phase 3)
- xbrl_facts: Append-only XBRL financial data points (Phase 3)
- patents: Append-only patent records from USPTO (Phase 5)
- github_repos: Append-only GitHub repository snapshots (Phase 6)
- earnings_transcripts: Append-only earnings call transcript data (Phase 7)
- job_postings: Lifecycle-tracked job posting data (Phase 8)
- data_source_status: Pipeline staleness tracking per data source (Phase 10)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ai_washer.db.base import AppendOnlyMixin, Base, DualTimestampMixin


class Company(Base):
    """Public company entity table.

    Not append-only -- allows updates to aliases, market_cap, sector.
    Per D-07: UUID primary keys.
    Per D-09: monetary values stored as BIGINT (cents).
    """

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cik: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    market_cap_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    aliases: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("true"))
    deactivation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DailyScore(DualTimestampMixin, Base):
    """Append-only daily composite AI washing score.

    Per D-06: monthly RANGE partitioning on scored_at.
    Per D-07: UUID primary keys (composite with scored_at for partitioning).
    Per D-08: dual timestamps (as_of_date, observed_date).

    NOTE: Uses DualTimestampMixin (not AppendOnlyMixin) because the PK
    structure is custom -- PostgreSQL requires the partition key in the PK.
    Actual monthly partitions are created in Plan 03's migration.
    """

    __tablename__ = "daily_scores"
    __table_args__ = (
        Index("ix_daily_scores_company_scored", "company_id", "scored_at"),
        {"postgresql_partition_by": "RANGE (scored_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    composite_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    signal_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    weights_used: Mapped[dict] = mapped_column(JSONB, nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SignalDetail(AppendOnlyMixin, Base):
    """Append-only individual signal score with evidence.

    Per D-05: JSONB for flexible evidence content.
    Per D-07: UUID primary keys (from AppendOnlyMixin).
    Per D-08: dual timestamps (from AppendOnlyMixin).
    """

    __tablename__ = "signal_details"
    __table_args__ = (
        Index(
            "ix_signal_details_company_type_date",
            "company_id",
            "signal_type",
            "as_of_date",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)


class PipelineRun(Base):
    """Operational tracking for batch pipeline runs.

    Not financial data -- no dual timestamps needed.
    Per D-07: UUID primary keys.
    """

    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    companies_processed: Mapped[int] = mapped_column(default=0)
    errors: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Filing(AppendOnlyMixin, Base):
    """Append-only SEC filing text and metadata.

    Stores structured section excerpts and metadata for 10-K, 10-Q, 8-K filings.
    Per D-07: UUID primary keys (from AppendOnlyMixin).
    Per D-08: dual timestamps (from AppendOnlyMixin).
    Sections stored as JSONB for flexible content.

    Unique constraint on (company_id, form_type, accession_no) ensures
    idempotent re-collection -- re-running for the same filing is a no-op.
    """

    __tablename__ = "sec_filings"
    __table_args__ = (
        Index(
            "ix_sec_filings_company_form_observed",
            "company_id",
            "form_type",
            "observed_date",
        ),
        Index(
            "uq_sec_filings_company_form_accession",
            "company_id",
            "form_type",
            "accession_no",
            unique=True,
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    form_type: Mapped[str] = mapped_column(String(10), nullable=False)
    accession_no: Mapped[str] = mapped_column(String(25), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_of_report: Mapped[date | None] = mapped_column(Date, nullable=True)
    sections: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collection_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class XBRLFact(AppendOnlyMixin, Base):
    """Append-only XBRL financial data point.

    Stores individual financial facts extracted from the SEC companyfacts API
    (e.g., R&D expense, CapEx, revenue for a specific fiscal period).
    Per D-07: UUID primary keys (from AppendOnlyMixin).
    Per D-08: dual timestamps (from AppendOnlyMixin).
    Per D-09: monetary values stored as BIGINT (cents).

    Unique constraint on (company_id, concept, end_date, fiscal_period)
    ensures dedup -- same fact from different filings is stored once.
    """

    __tablename__ = "xbrl_facts"
    __table_args__ = (
        Index(
            "ix_xbrl_facts_company_concept_end",
            "company_id",
            "concept",
            "end_date",
        ),
        Index(
            "uq_xbrl_facts_company_concept_end_fp",
            "company_id",
            "concept",
            "end_date",
            "fiscal_period",
            unique=True,
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    concept: Mapped[str] = mapped_column(String(50), nullable=False)
    tag: Mapped[str] = mapped_column(String(100), nullable=False)
    value_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String(5), nullable=False)
    form_type: Mapped[str] = mapped_column(String(10), nullable=False)
    filed_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    accession_no: Mapped[str] = mapped_column(String(25), nullable=False)


class Patent(AppendOnlyMixin, Base):
    """Append-only patent record from USPTO PatentsView.

    Stores granted patents with AI-related CPC codes for patent gap scoring.
    Unique constraint on (company_id, patent_id) ensures idempotent collection.
    Per D-07: UUID primary keys (from AppendOnlyMixin).
    Per D-08: dual timestamps (from AppendOnlyMixin).
    """

    __tablename__ = "patents"
    __table_args__ = (
        Index("ix_patents_company_date", "company_id", "patent_date"),
        Index(
            "uq_patents_company_patent_id",
            "company_id",
            "patent_id",
            unique=True,
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    patent_id: Mapped[str] = mapped_column(String(20), nullable=False)
    patent_title: Mapped[str] = mapped_column(String(500), nullable=False)
    patent_date: Mapped[date] = mapped_column(Date, nullable=False)
    assignee_organization: Mapped[str] = mapped_column(String(500), nullable=False)
    cpc_codes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
    collection_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class EarningsTranscript(AppendOnlyMixin, Base):
    """Append-only earnings call transcript data.

    Stores structured transcript text and metadata for earnings calls.
    Unique constraint on (company_id, fiscal_year, fiscal_quarter) ensures
    idempotent collection -- re-running for the same quarter is a no-op.
    Per D-07: UUID primary keys (from AppendOnlyMixin).
    Per D-08: dual timestamps (from AppendOnlyMixin).
    """

    __tablename__ = "earnings_transcripts"
    __table_args__ = (
        Index(
            "ix_earnings_transcripts_company_date",
            "company_id",
            "observed_date",
        ),
        Index(
            "uq_earnings_transcripts_company_year_quarter",
            "company_id",
            "fiscal_year",
            "fiscal_quarter",
            unique=True,
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    transcript_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transcript_text: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    source: Mapped[str] = mapped_column(String(50), nullable=False, server_default="earningscall")
    collection_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class GitHubRepo(AppendOnlyMixin, Base):
    """Append-only GitHub repository snapshot.

    Stores individual repository data collected from GitHub REST API for
    GitHub activity scoring. Unique constraint on (company_id, repo_full_name,
    observed_date) ensures idempotent daily collection.
    Per D-07: UUID primary keys (from AppendOnlyMixin).
    Per D-08: dual timestamps (from AppendOnlyMixin).
    """

    __tablename__ = "github_repos"
    __table_args__ = (
        Index(
            "ix_github_repos_company_date",
            "company_id",
            "observed_date",
        ),
        Index(
            "uq_github_repos_company_repo_observed",
            "company_id",
            "repo_full_name",
            "observed_date",
            unique=True,
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language_bytes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_fork: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stargazers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ml_frameworks: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
    collection_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


class JobPosting(Base):
    """Lifecycle-tracked job posting data for job mismatch scoring.

    NOT append-only -- lifecycle tracking requires updates to last_seen
    and is_active columns when a posting disappears or reappears.
    Per D-07: UUID primary keys.
    Unique constraint on dedup_hash ensures idempotent collection.
    """

    __tablename__ = "job_postings"
    __table_args__ = (
        Index("ix_job_postings_company_date", "company_id", "first_seen"),
        Index("uq_job_postings_dedup_hash", "dedup_hash", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company_name_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    job_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_site: Mapped[str] = mapped_column(String(50), nullable=False)
    role_classification: Mapped[str] = mapped_column(String(20), nullable=False)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("true")
    )
    collection_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DataSourceStatus(Base):
    """Operational staleness tracking for each data source.

    Not financial data -- operational table like PipelineRun.
    Tracks when each data source last succeeded/failed and whether it is stale
    relative to its expected refresh cadence.
    Per D-07: UUID primary keys.
    """

    __tablename__ = "data_source_status"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expected_cadence_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, server_default=sa.text("false"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
