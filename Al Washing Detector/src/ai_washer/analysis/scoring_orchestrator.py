"""Scoring orchestrator: thin DB layer bridging pure scorers to the database.

This is the ONLY module in analysis/ that touches the database. All scoring
logic lives in the pure functions:
- compute_sec_filing_score (sec_filing_scorer.py)
- compute_compute_spending_score (compute_spending_scorer.py)
- compute_patent_gap_score (patent_gap_scorer.py)
- compute_github_activity_score (github_activity_scorer.py)
- compute_earnings_vagueness_score (earnings_vagueness_scorer.py)
- compute_job_mismatch_score (job_mismatch_scorer.py)

The orchestrator reads Filing, XBRLFact, Patent, GitHubRepo,
EarningsTranscript, and JobPosting rows, converts them to typed inputs,
calls the pure scorers, and writes SignalDetail rows with evidence JSONB.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_washer.analysis.composite_scorer import CompositeResult, compute_composite_score
from ai_washer.analysis.compute_spending_scorer import (
    compute_compute_spending_score,
)
from ai_washer.analysis.job_mismatch_scorer import compute_job_mismatch_score
from ai_washer.analysis.earnings_vagueness_scorer import (
    compute_earnings_vagueness_score,
)
from ai_washer.analysis.finbert_analyzer import FinBERTAnalyzer
from ai_washer.analysis.github_activity_scorer import (
    compute_github_activity_score,
)
from ai_washer.analysis.patent_gap_scorer import compute_patent_gap_score
from ai_washer.analysis.sec_filing_scorer import (
    compute_keyword_counts_by_year,
    compute_sec_filing_score,
)
from ai_washer.analysis.types import FilingForScoring, SignalResult
from ai_washer.config import ScoringConfig
from ai_washer.db.models import (
    Company,
    DailyScore,
    EarningsTranscript,
    Filing,
    GitHubRepo,
    JobPosting,
    Patent,
    SignalDetail,
    XBRLFact,
)

logger = structlog.get_logger(__name__)


class ScoringOrchestrator:
    """Bridges pure scoring functions to the database.

    Reads Filing + XBRLFact rows, converts to typed inputs,
    calls pure scorers, writes SignalDetail rows.
    """

    def __init__(
        self,
        session: Session,
        config: ScoringConfig | None = None,
        scoring_date: date | None = None,
        run_id: uuid.UUID | None = None,
    ) -> None:
        self._session = session
        self._config = config or ScoringConfig()
        self._scoring_date = scoring_date or date.today()
        self._run_id = run_id or uuid.uuid4()
        self._finbert: FinBERTAnalyzer | None = None

    @property
    def run_id(self) -> uuid.UUID:
        """Expose run_id for external callers (e.g., integration tests)."""
        return self._run_id

    def _load_filings(self, company_id: uuid.UUID) -> list[FilingForScoring]:
        """Load Filing rows and convert to FilingForScoring.

        Uses period_of_report.year for 10-K/10-Q (Pitfall 5), falling back
        to filing_date.year when period_of_report is None.
        """
        stmt = (
            select(Filing)
            .where(
                Filing.company_id == company_id,
                Filing.form_type.in_(("10-K", "10-Q")),
            )
            .order_by(Filing.filing_date)
        )
        orm_filings = self._session.execute(stmt).scalars().all()

        result: list[FilingForScoring] = []
        for f in orm_filings:
            year = f.period_of_report.year if f.period_of_report is not None else f.filing_date.year
            result.append(FilingForScoring(year=year, sections=f.sections))

        return sorted(result, key=lambda ffs: ffs.year)

    def _load_xbrl_facts(self, company_id: uuid.UUID, concept: str) -> list[tuple[int, str, int]]:
        """Load XBRLFact rows for a concept and return typed tuples.

        Returns (fiscal_year, fiscal_period, value_cents) sorted by year.
        """
        stmt = (
            select(XBRLFact)
            .where(
                XBRLFact.company_id == company_id,
                XBRLFact.concept == concept,
            )
            .order_by(XBRLFact.fiscal_year)
        )
        facts = self._session.execute(stmt).scalars().all()
        return [(fact.fiscal_year, fact.fiscal_period, fact.value_cents) for fact in facts]

    def _load_patent_counts(self, company_id: uuid.UUID) -> dict[int, int]:
        """Load patent counts per grant year for a company.

        Queries Patent table, groups by patent_date.year, returns
        {year: count} dict for the patent gap scorer.
        """
        from sqlalchemy import extract, func

        stmt = (
            select(
                extract("year", Patent.patent_date).label("grant_year"),
                func.count(Patent.patent_id).label("cnt"),
            )
            .where(Patent.company_id == company_id)
            .group_by(extract("year", Patent.patent_date))
        )
        rows = self._session.execute(stmt).all()
        return {int(row.grant_year): int(row.cnt) for row in rows}

    def _load_github_snapshot(
        self, company_id: uuid.UUID
    ) -> tuple[int, float, int | None, list[str]] | None:
        """Load GitHub repo data and aggregate for scoring.

        Queries GitHubRepo rows for the most recent observed_date.
        Returns a tuple of (repo_count, ml_language_ratio,
        days_since_last_push, ml_frameworks_found), or None if no rows.
        """
        from datetime import datetime as dt_cls
        from datetime import timezone as tz_cls

        from sqlalchemy import func

        # Find the most recent observed_date for this company
        max_date_stmt = select(func.max(GitHubRepo.observed_date)).where(
            GitHubRepo.company_id == company_id
        )
        max_date = self._session.execute(max_date_stmt).scalar_one_or_none()

        if max_date is None:
            return None

        # Load repos for the most recent snapshot
        stmt = select(GitHubRepo).where(
            GitHubRepo.company_id == company_id,
            GitHubRepo.observed_date == max_date,
        )
        repos = self._session.execute(stmt).scalars().all()

        if not repos:
            return None

        repo_count = len(repos)

        # Aggregate language bytes across all repos
        total_ml_bytes = 0
        total_bytes = 0
        all_frameworks: set[str] = set()
        most_recent_push: dt_cls | None = None

        ml_languages = {"Python", "R", "Julia", "C++", "Rust", "Jupyter Notebook"}

        for repo in repos:
            lang_bytes = repo.language_bytes or {}
            for lang, byte_count in lang_bytes.items():
                total_bytes += byte_count
                if lang in ml_languages:
                    total_ml_bytes += byte_count

            frameworks = repo.ml_frameworks
            if isinstance(frameworks, list):
                all_frameworks.update(frameworks)

            if repo.pushed_at is not None:
                if most_recent_push is None or repo.pushed_at > most_recent_push:
                    most_recent_push = repo.pushed_at

        ml_language_ratio = total_ml_bytes / total_bytes if total_bytes > 0 else 0.0

        days_since_last_push: int | None = None
        if most_recent_push is not None:
            ref_dt = dt_cls(
                self._scoring_date.year,
                self._scoring_date.month,
                self._scoring_date.day,
                tzinfo=tz_cls.utc,
            )
            delta = ref_dt - most_recent_push
            days_since_last_push = delta.days

        return (
            repo_count,
            ml_language_ratio,
            days_since_last_push,
            sorted(all_frameworks),
        )

    def _ensure_finbert(self) -> FinBERTAnalyzer:
        """Lazy-create FinBERTAnalyzer on first use."""
        if self._finbert is None:
            self._finbert = FinBERTAnalyzer()
        return self._finbert

    def _load_earnings_transcripts(self, company_id: uuid.UUID) -> list[dict]:
        """Load EarningsTranscript rows and return transcript_text dicts.

        Returns list of transcript_text JSONB dicts ordered by
        fiscal_year desc, fiscal_quarter desc. Empty list if none found.
        """
        stmt = (
            select(EarningsTranscript)
            .where(EarningsTranscript.company_id == company_id)
            .order_by(
                EarningsTranscript.fiscal_year.desc(),
                EarningsTranscript.fiscal_quarter.desc(),
            )
        )
        rows = self._session.execute(stmt).scalars().all()
        return [row.transcript_text for row in rows]

    def _load_job_postings(
        self, company_id: uuid.UUID
    ) -> tuple[int, int, int, float] | None:
        """Load job posting stats for scoring.

        Returns (ai_role_count, marketing_role_count, total_count, ghost_ratio)
        or None if no job postings exist for this company.
        """
        stmt = select(JobPosting).where(JobPosting.company_id == company_id)
        postings = list(self._session.execute(stmt).scalars().all())

        if not postings:
            return None

        total_count = len(postings)
        ai_role_count = sum(1 for p in postings if p.role_classification == "engineering")
        marketing_role_count = sum(1 for p in postings if p.role_classification == "marketing")

        # Ghost ratio: active postings older than threshold
        ghost_threshold = self._config.job_mismatch.ghost_days_threshold
        active_postings = [p for p in postings if p.is_active]
        if active_postings:
            ghost_count = sum(
                1
                for p in active_postings
                if (self._scoring_date - p.first_seen).days > ghost_threshold
            )
            ghost_ratio = ghost_count / len(active_postings)
        else:
            ghost_ratio = 0.0

        return (ai_role_count, marketing_role_count, total_count, ghost_ratio)

    def score_company(self, company_id: uuid.UUID, ticker: str) -> list[SignalResult]:
        """Score a single company on both signals.

        Loads filings and XBRL facts, calls both pure scorers, returns
        non-None results. Shares keyword counts between SEC and compute
        scorers for consistency.
        """
        filings = self._load_filings(company_id)
        rd_facts = self._load_xbrl_facts(company_id, "rd_expense")
        capex_facts = self._load_xbrl_facts(company_id, "capex")

        results: list[SignalResult] = []

        # SEC filing score
        sec_cfg = self._config.sec_filing
        sec_result = compute_sec_filing_score(
            filings,
            rd_facts,
            scoring_year=self._scoring_date.year,
            window_years=sec_cfg.window_years,
            section_weights=sec_cfg.section_weights,
            sigmoid_midpoint=sec_cfg.sigmoid_midpoint,
            sigmoid_steepness=sec_cfg.sigmoid_steepness,
        )

        if sec_result is not None:
            results.append(sec_result)
            logger.info(
                "signal_scored",
                company_id=str(company_id),
                ticker=ticker,
                signal_type=sec_result.signal_type,
                score=sec_result.score,
            )
        else:
            logger.info(
                "signal_skipped",
                company_id=str(company_id),
                ticker=ticker,
                signal_type="sec_filing",
                reason="insufficient_data",
            )

        # Shared keyword counts for compute scorer
        kw_by_year = compute_keyword_counts_by_year(filings)
        ai_keyword_counts: dict[int, float] = {
            year: kfr.total_weighted_count for year, kfr in kw_by_year.items()
        }

        # Compute spending score
        comp_cfg = self._config.compute_spending
        comp_result = compute_compute_spending_score(
            filings,
            capex_facts,
            ai_keyword_counts,
            scoring_year=self._scoring_date.year,
            window_years=comp_cfg.window_years,
            capex_weight=comp_cfg.capex_weight,
            cloud_mention_weight=comp_cfg.cloud_mention_weight,
            sigmoid_midpoint=comp_cfg.sigmoid_midpoint,
            sigmoid_steepness=comp_cfg.sigmoid_steepness,
        )

        if comp_result is not None:
            results.append(comp_result)
            logger.info(
                "signal_scored",
                company_id=str(company_id),
                ticker=ticker,
                signal_type=comp_result.signal_type,
                score=comp_result.score,
            )
        else:
            logger.info(
                "signal_skipped",
                company_id=str(company_id),
                ticker=ticker,
                signal_type="compute_spending",
                reason="insufficient_data",
            )

        # Patent gap score
        patent_counts = self._load_patent_counts(company_id)
        pat_cfg = self._config.patent_gap
        pat_result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_keyword_counts,
            scoring_year=self._scoring_date.year,
            window_years=pat_cfg.window_years,
            sigmoid_midpoint=pat_cfg.sigmoid_midpoint,
            sigmoid_steepness=pat_cfg.sigmoid_steepness,
        )

        if pat_result is not None:
            results.append(pat_result)
            logger.info(
                "signal_scored",
                company_id=str(company_id),
                ticker=ticker,
                signal_type=pat_result.signal_type,
                score=pat_result.score,
            )
        else:
            logger.info(
                "signal_skipped",
                company_id=str(company_id),
                ticker=ticker,
                signal_type="patent_gap",
                reason="insufficient_data",
            )

        # GitHub activity score
        gh_snapshot = self._load_github_snapshot(company_id)

        if gh_snapshot is None:
            logger.info(
                "signal_skipped",
                company_id=str(company_id),
                ticker=ticker,
                signal_type="github_activity",
                reason="no_github_data",
            )
        else:
            gh_repo_count, gh_ml_ratio, gh_days_push, gh_frameworks = gh_snapshot

            # Use current scoring year's AI keyword intensity
            scoring_year = self._scoring_date.year
            ai_claim_intensity = ai_keyword_counts.get(scoring_year, 0.0)

            gh_cfg = self._config.github_activity
            gh_result = compute_github_activity_score(
                repo_count=gh_repo_count,
                ml_language_ratio=gh_ml_ratio,
                days_since_last_push=gh_days_push,
                ml_frameworks_found=gh_frameworks,
                ai_claim_intensity=ai_claim_intensity,
                scoring_year=scoring_year,
                recency_decay_days=gh_cfg.recency_decay_days,
                sigmoid_midpoint=gh_cfg.sigmoid_midpoint,
                sigmoid_steepness=gh_cfg.sigmoid_steepness,
            )

            if gh_result is not None:
                results.append(gh_result)
                logger.info(
                    "signal_scored",
                    company_id=str(company_id),
                    ticker=ticker,
                    signal_type=gh_result.signal_type,
                    score=gh_result.score,
                )
            else:
                logger.info(
                    "signal_skipped",
                    company_id=str(company_id),
                    ticker=ticker,
                    signal_type="github_activity",
                    reason="insufficient_data",
                )

        # Earnings vagueness score
        transcripts = self._load_earnings_transcripts(company_id)

        if not transcripts:
            logger.info(
                "signal_skipped",
                company_id=str(company_id),
                ticker=ticker,
                signal_type="earnings_vagueness",
                reason="no_earnings_data",
            )
        else:
            # Concatenate all transcript full_text into one block
            full_texts = [
                t.get("full_text", "") or ""
                for t in transcripts
                if isinstance(t.get("full_text"), str)
            ]
            combined_text = " ".join(full_texts)

            if combined_text.strip():
                # Run FinBERT sentiment analysis
                analyzer = self._ensure_finbert()
                sentiment_result = analyzer.analyze_text(combined_text)

                # Get ai_claim_intensity from shared keyword counts
                # CRITICAL: Use None when SEC data unavailable (not 0.0)
                scoring_year = self._scoring_date.year
                ai_claim_intensity: float | None = ai_keyword_counts.get(scoring_year)

                earn_cfg = self._config.earnings_vagueness
                earn_result = compute_earnings_vagueness_score(
                    transcript_text={"full_text": combined_text},
                    sentiment_result=sentiment_result,
                    ai_claim_intensity=ai_claim_intensity,
                    buzzword_weight=earn_cfg.buzzword_weight,
                    sentiment_weight=earn_cfg.sentiment_weight,
                    sigmoid_midpoint=earn_cfg.sigmoid_midpoint,
                    sigmoid_steepness=earn_cfg.sigmoid_steepness,
                )

                if earn_result is not None:
                    results.append(earn_result)
                    logger.info(
                        "signal_scored",
                        company_id=str(company_id),
                        ticker=ticker,
                        signal_type=earn_result.signal_type,
                        score=earn_result.score,
                    )
                else:
                    logger.info(
                        "signal_skipped",
                        company_id=str(company_id),
                        ticker=ticker,
                        signal_type="earnings_vagueness",
                        reason="scorer_returned_none",
                    )
            else:
                logger.info(
                    "signal_skipped",
                    company_id=str(company_id),
                    ticker=ticker,
                    signal_type="earnings_vagueness",
                    reason="no_transcript_text",
                )

        # Job mismatch score
        job_stats = self._load_job_postings(company_id)

        if job_stats is None:
            logger.info(
                "signal_skipped",
                company_id=str(company_id),
                ticker=ticker,
                signal_type="job_mismatch",
                reason="no_job_data",
            )
        else:
            ai_roles, mkt_roles, total_roles, ghost_rat = job_stats

            scoring_year = self._scoring_date.year
            ai_claim_intensity = ai_keyword_counts.get(scoring_year, 0.0)

            job_cfg = self._config.job_mismatch
            job_result = compute_job_mismatch_score(
                ai_role_count=ai_roles,
                marketing_role_count=mkt_roles,
                total_role_count=total_roles,
                ghost_ratio=ghost_rat,
                ai_claim_intensity=ai_claim_intensity,
                scoring_year=scoring_year,
                ghost_penalty_weight=job_cfg.ghost_penalty_weight,
                engineering_weight=job_cfg.engineering_weight,
                hiring_intensity_weight=job_cfg.hiring_intensity_weight,
                sigmoid_midpoint=job_cfg.sigmoid_midpoint,
                sigmoid_steepness=job_cfg.sigmoid_steepness,
            )

            if job_result is not None:
                results.append(job_result)
                logger.info(
                    "signal_scored",
                    company_id=str(company_id),
                    ticker=ticker,
                    signal_type=job_result.signal_type,
                    score=job_result.score,
                )
            else:
                logger.info(
                    "signal_skipped",
                    company_id=str(company_id),
                    ticker=ticker,
                    signal_type="job_mismatch",
                    reason="insufficient_data",
                )

        return results

    def persist_signals(self, company_id: uuid.UUID, results: list[SignalResult]) -> int:
        """Write SignalDetail rows, skipping existing (idempotent).

        Checks for existing rows matching (company_id, signal_type, as_of_date)
        before inserting. Returns count of new rows inserted.
        """
        inserted = 0
        for result in results:
            # Check for existing row
            exists_stmt = select(SignalDetail).where(
                SignalDetail.company_id == company_id,
                SignalDetail.signal_type == result.signal_type,
                SignalDetail.as_of_date == self._scoring_date,
            )
            existing = self._session.execute(exists_stmt).scalar_one_or_none()

            if existing is not None:
                logger.info(
                    "signal_already_exists",
                    company_id=str(company_id),
                    signal_type=result.signal_type,
                    as_of_date=str(self._scoring_date),
                )
                continue

            detail = SignalDetail(
                company_id=company_id,
                signal_type=result.signal_type,
                score=result.score,
                evidence=result.evidence,
                run_id=self._run_id,
                as_of_date=self._scoring_date,
            )
            self._session.add(detail)
            self._session.flush()
            inserted += 1

        return inserted

    def persist_composite(
        self, company_id: uuid.UUID, result: CompositeResult
    ) -> bool:
        """Write a DailyScore row for the composite, skipping if already exists.

        Idempotency: checks for existing DailyScore matching
        (company_id, func.date(scored_at) == scoring_date) before inserting.
        Pitfall 4: No unique constraint -- must use EXISTS check.
        Pitfall 5: scored_at is DateTime(timezone=True), use func.date().

        Args:
            company_id: UUID of the company.
            result: CompositeResult from the pure composite scorer.

        Returns:
            True if a new row was inserted, False if already existed.
        """
        # Check for existing row on the same day
        exists_stmt = select(DailyScore).where(
            DailyScore.company_id == company_id,
            func.date(DailyScore.scored_at) == self._scoring_date,
        )
        existing = self._session.execute(exists_stmt).scalar_one_or_none()

        if existing is not None:
            logger.info(
                "composite_already_exists",
                company_id=str(company_id),
                as_of_date=str(self._scoring_date),
            )
            return False

        scored_at = datetime(
            self._scoring_date.year,
            self._scoring_date.month,
            self._scoring_date.day,
            tzinfo=timezone.utc,
        )

        row = DailyScore(
            company_id=company_id,
            scored_at=scored_at,
            composite_score=result.score,
            signal_breakdown=result.signal_breakdown,
            confidence=result.confidence,
            weights_used=result.weights_used,
            run_id=self._run_id,
            as_of_date=self._scoring_date,
        )
        self._session.add(row)
        self._session.flush()
        return True

    def compute_and_persist_composite(
        self,
        company_id: uuid.UUID,
        signal_results: list[SignalResult],
    ) -> CompositeResult | None:
        """Compute composite score and persist DailyScore row.

        Calls the pure compute_composite_score function, then persists
        via persist_composite. Logs the result.

        Args:
            company_id: UUID of the company.
            signal_results: Individual signal scores for the company.

        Returns:
            CompositeResult if computed, None if no signals available.
        """
        result = compute_composite_score(
            signal_results,
            self._config.weights,
            low_risk_threshold=self._config.low_risk_threshold,
            high_risk_threshold=self._config.high_risk_threshold,
            strong_short_threshold=self._config.strong_short_threshold,
        )

        if result is None:
            logger.info(
                "composite_skipped",
                company_id=str(company_id),
                reason="no_signals",
            )
            return None

        self.persist_composite(company_id, result)

        logger.info(
            "composite_scored",
            company_id=str(company_id),
            composite_score=result.score,
            risk_band=result.risk_band,
            confidence=result.confidence,
        )

        return result

    def score_all(self) -> list[tuple[str, list[SignalResult]]]:
        """Score all active companies with CIK.

        Iterates companies sorted by ticker for determinism. Scores each,
        persists signals, and returns results list.
        """
        stmt = (
            select(Company)
            .where(
                Company.is_active == True,  # noqa: E712
                Company.cik.isnot(None),
            )
            .order_by(Company.ticker)
        )
        companies = self._session.execute(stmt).scalars().all()

        all_results: list[tuple[str, list[SignalResult]]] = []
        total_signals = 0
        total_composites = 0

        for company in companies:
            results = self.score_company(company.id, company.ticker)
            count = self.persist_signals(company.id, results)
            total_signals += count

            composite = self.compute_and_persist_composite(company.id, results)
            if composite is not None:
                total_composites += 1

            all_results.append((company.ticker, results))

        logger.info(
            "scoring_complete",
            companies_scored=len(companies),
            signals_persisted=total_signals,
            composites_persisted=total_composites,
            run_id=str(self._run_id),
        )

        return all_results
