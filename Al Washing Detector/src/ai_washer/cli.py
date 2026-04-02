"""CLI entry point for the ai-washer command."""

import typer

from ai_washer import __version__

app = typer.Typer(
    name="ai-washer",
    help="AI Washing Detector - scores companies on AI claim vs investment gap.",
    no_args_is_help=True,
)

universe_app = typer.Typer(help="Manage the target company universe.")
app.add_typer(universe_app, name="universe")

collect_app = typer.Typer(help="Collect SEC filings and XBRL data.")
app.add_typer(collect_app, name="collect")

score_app = typer.Typer(help="Score companies on SEC filing mismatch and compute spending gap.")
app.add_typer(score_app, name="score")

patent_app = typer.Typer(help="Collect and manage patent data.")
app.add_typer(patent_app, name="patent")

github_app = typer.Typer(help="Collect and manage GitHub repository data.")
app.add_typer(github_app, name="github")

earnings_app = typer.Typer(help="Collect earnings call transcripts.")
app.add_typer(earnings_app, name="earnings")

job_app = typer.Typer(help="Collect job posting data.")
app.add_typer(job_app, name="job")

pipeline_app = typer.Typer(help="Run and monitor the daily pipeline.")
app.add_typer(pipeline_app, name="pipeline")


@app.command()
def version():
    """Print the current version."""
    typer.echo(f"ai-washer {__version__}")


@app.command()
def check_config():
    """Validate configuration and print loaded settings."""
    from ai_washer.config import load_app_settings, load_scoring_config

    app_settings = load_app_settings()
    scoring = load_scoring_config()
    typer.echo(f"Database URL: {app_settings.database_url[:20]}...")
    typer.echo(f"EDGAR identity: {app_settings.edgar_identity}")
    typer.echo(f"Signal weights: {scoring.weights.model_dump()}")
    typer.echo("Configuration valid.")


@universe_app.command()
def scan(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without writing to DB"
    ),
):
    """Run a full universe scan: EFTS search -> market cap filter -> entity resolution -> persist."""
    from ai_washer.config import UniverseSettings, load_app_settings
    from ai_washer.universe.builder import UniverseBuilder

    app_settings = load_app_settings()
    universe_settings = UniverseSettings()
    builder = UniverseBuilder(settings=universe_settings, app_settings=app_settings)

    if dry_run:
        typer.echo("DRY RUN: Scanning EFTS for AI-claiming companies...")
        hits = builder.scan()
        typer.echo(f"Found {len(hits)} unique companies from EFTS search")
        hits_with_cap = builder.filter_market_cap(hits)
        typer.echo(f"After market cap filter: {len(hits_with_cap)} companies")
        typer.echo("DRY RUN complete. No database changes made.")
        return

    typer.echo("Starting universe scan...")
    result = builder.build()
    typer.echo(f"Scan date: {result.scan_date}")
    typer.echo(f"Companies in universe: {result.company_count}")
    typer.echo(f"  New: {result.new_count}")
    typer.echo(f"  Updated: {result.updated_count}")
    typer.echo(f"  Deactivated: {result.deactivated_count}")
    typer.echo(f"  Skipped (no market cap): {result.skipped_no_market_cap}")


@universe_app.command(name="list")
def list_companies(
    active_only: bool = typer.Option(True, "--active/--all", help="Show only active companies"),
    limit: int = typer.Option(50, "--limit", help="Maximum number of companies to show"),
):
    """List companies in the target universe."""
    from sqlalchemy import select

    from ai_washer.config import load_app_settings
    from ai_washer.db.models import Company
    from ai_washer.db.session import create_engine_from_settings, get_session_factory

    settings = load_app_settings()
    engine = create_engine_from_settings(settings)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        stmt = select(Company).order_by(Company.ticker)
        if active_only:
            stmt = stmt.where(Company.is_active == True)  # noqa: E712
        stmt = stmt.limit(limit)
        companies = session.execute(stmt).scalars().all()

        typer.echo(f"{'Ticker':<10} {'Name':<40} {'CIK':<12} {'Market Cap ($M)':<15} {'Active'}")
        typer.echo("-" * 90)
        for c in companies:
            cap_str = f"{c.market_cap_cents / 100_000_000:.0f}" if c.market_cap_cents else "N/A"
            typer.echo(
                f"{c.ticker:<10} {c.name[:38]:<40} {c.cik or 'N/A':<12} {cap_str:<15} {c.is_active}"
            )

        typer.echo(f"\nShowing {len(companies)} companies")


@universe_app.command()
def inspect(
    identifier: str = typer.Argument(help="Company ticker or CIK to inspect"),
):
    """Show detailed information for a single company including aliases."""
    import json

    from sqlalchemy import select

    from ai_washer.config import load_app_settings
    from ai_washer.db.models import Company
    from ai_washer.db.session import create_engine_from_settings, get_session_factory

    settings = load_app_settings()
    engine = create_engine_from_settings(settings)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        stmt = select(Company).where(
            (Company.ticker == identifier.upper()) | (Company.cik == identifier)
        )
        company = session.execute(stmt).scalar_one_or_none()

        if company is None:
            typer.echo(f"Company not found: {identifier}", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Ticker:    {company.ticker}")
        typer.echo(f"Name:      {company.name}")
        typer.echo(f"CIK:       {company.cik or 'N/A'}")
        typer.echo(f"Sector:    {company.sector or 'N/A'}")
        cap_str = (
            f"${company.market_cap_cents / 100_000_000:.0f}M" if company.market_cap_cents else "N/A"
        )
        typer.echo(f"Market Cap: {cap_str}")
        typer.echo(f"Active:    {company.is_active}")
        if company.deactivation_reason:
            typer.echo(f"Deactivation: {company.deactivation_reason}")
        typer.echo(f"Aliases:   {json.dumps(company.aliases, indent=2)}")
        typer.echo(f"Created:   {company.created_at}")
        typer.echo(f"Updated:   {company.updated_at}")


# ---------------------------------------------------------------------------
# collect subcommands
# ---------------------------------------------------------------------------


@collect_app.command(name="company")
def collect_company(
    identifier: str = typer.Argument(help="Company ticker or CIK to collect filings for"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without writing to DB"
    ),
):
    """Collect SEC filings and XBRL data for a single company."""
    from sqlalchemy import select

    from ai_washer.config import load_app_settings
    from ai_washer.db.models import Company
    from ai_washer.db.session import create_engine_from_settings, get_session_factory
    from ai_washer.ingestion.filing_collector import FilingCollector

    app_settings = load_app_settings()
    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        stmt = select(Company).where(
            (Company.ticker == identifier.upper()) | (Company.cik == identifier)
        )
        company = session.execute(stmt).scalar_one_or_none()

        if company is None:
            typer.echo(f"Company not found: {identifier}", err=True)
            raise typer.Exit(code=1)

        if company.cik is None:
            typer.echo(
                f"Company {company.ticker} has no CIK -- cannot collect filings",
                err=True,
            )
            raise typer.Exit(code=1)

        # Capture values before session closes
        company_id = company.id
        company_ticker = company.ticker
        company_cik = company.cik

    if dry_run:
        typer.echo(f"DRY RUN: Would collect filings for {company_ticker} (CIK: {company_cik})")
        typer.echo("Filing types: 10-K, 10-Q, 8-K")
        typer.echo("XBRL concepts: rd_expense, capex, revenue")
        return

    collector = FilingCollector(app_settings=app_settings)
    result = collector.collect_for_company(
        company_id=company_id,
        cik=company_cik,
        ticker=company_ticker,
    )

    typer.echo(f"Company: {company_ticker} (CIK: {company_cik})")
    typer.echo(f"Filings collected: {result.filing_count}")
    typer.echo(f"XBRL facts extracted: {result.xbrl_fact_count}")
    typer.echo(f"Skipped (already collected): {result.skipped_count}")
    if result.errors:
        typer.echo(f"Errors: {len(result.errors)}")
        for err in result.errors:
            typer.echo(f"  - {err}", err=True)


@collect_app.command(name="all")
def collect_all_cmd(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without writing to DB"
    ),
):
    """Collect SEC filings and XBRL data for all active companies in universe."""
    from ai_washer.config import load_app_settings
    from ai_washer.ingestion.filing_collector import FilingCollector

    app_settings = load_app_settings()

    if dry_run:
        from sqlalchemy import func, select

        from ai_washer.db.models import Company
        from ai_washer.db.session import create_engine_from_settings, get_session_factory

        engine = create_engine_from_settings(app_settings)
        sf = get_session_factory(engine)
        with sf() as session:
            count = session.execute(
                select(func.count()).where(
                    Company.is_active == True,  # noqa: E712
                    Company.cik.isnot(None),
                )
            ).scalar()
        typer.echo(f"DRY RUN: Would collect filings for {count} active companies")
        return

    collector = FilingCollector(app_settings=app_settings)
    results = collector.collect_all()

    total_filings = sum(r.filing_count for r in results)
    total_xbrl = sum(r.xbrl_fact_count for r in results)
    total_skipped = sum(r.skipped_count for r in results)
    total_errors = sum(len(r.errors) for r in results)

    typer.echo(f"Collection complete for {len(results)} companies")
    typer.echo(f"Total filings: {total_filings}")
    typer.echo(f"Total XBRL facts: {total_xbrl}")
    typer.echo(f"Total skipped: {total_skipped}")
    if total_errors:
        typer.echo(f"Total errors: {total_errors}")


# ---------------------------------------------------------------------------
# score subcommands
# ---------------------------------------------------------------------------


@score_app.command(name="company")
def score_company_cmd(
    identifier: str = typer.Argument(help="Company ticker or CIK to score"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Compute scores without writing to DB"),
    scoring_date: str = typer.Option(
        None, "--date", help="Scoring date (YYYY-MM-DD), defaults to today"
    ),
):
    """Score a single company on SEC filing mismatch and compute spending gap."""
    from datetime import date as date_type

    from sqlalchemy import select

    from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator
    from ai_washer.config import load_app_settings, load_scoring_config
    from ai_washer.db.models import Company
    from ai_washer.db.session import create_engine_from_settings, get_session_factory

    app_settings = load_app_settings()
    scoring_cfg = load_scoring_config()
    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)

    parsed_date = date_type.fromisoformat(scoring_date) if scoring_date is not None else None

    with session_factory() as session:
        stmt = select(Company).where(
            (Company.ticker == identifier.upper()) | (Company.cik == identifier)
        )
        company = session.execute(stmt).scalar_one_or_none()

        if company is None:
            typer.echo(f"Company not found: {identifier}", err=True)
            raise typer.Exit(code=1)

        if company.cik is None:
            typer.echo(
                f"Company {company.ticker} has no CIK -- cannot score",
                err=True,
            )
            raise typer.Exit(code=1)

        orch = ScoringOrchestrator(
            session=session,
            config=scoring_cfg,
            scoring_date=parsed_date,
        )

        results = orch.score_company(company.id, company.ticker)

        if not results:
            typer.echo("No scores produced (insufficient data)")
            return

        for r in results:
            typer.echo(f"{company.ticker}  {r.signal_type:<20} score={r.score}")

        if not dry_run:
            count = orch.persist_signals(company.id, results)
            session.commit()
            typer.echo(f"Persisted {count} signal(s)")
        else:
            typer.echo("DRY RUN: scores computed but not persisted")


@score_app.command(name="all")
def score_all_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Compute scores without writing to DB"),
    scoring_date: str = typer.Option(
        None, "--date", help="Scoring date (YYYY-MM-DD), defaults to today"
    ),
):
    """Score all active companies in the universe."""
    from datetime import date as date_type

    from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator
    from ai_washer.config import load_app_settings, load_scoring_config
    from ai_washer.db.session import create_engine_from_settings, get_session_factory

    app_settings = load_app_settings()
    scoring_cfg = load_scoring_config()
    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)

    parsed_date = date_type.fromisoformat(scoring_date) if scoring_date is not None else None

    with session_factory() as session:
        orch = ScoringOrchestrator(
            session=session,
            config=scoring_cfg,
            scoring_date=parsed_date,
        )

        all_results = orch.score_all()

        total_companies = len(all_results)
        total_signals = sum(len(r) for _, r in all_results)
        skipped = sum(1 for _, r in all_results if not r)

        for ticker, results in all_results:
            for r in results:
                typer.echo(f"{ticker:<10} {r.signal_type:<20} score={r.score}")

        typer.echo(f"\nCompanies scored: {total_companies}")
        typer.echo(f"Signals produced: {total_signals}")
        typer.echo(f"Companies with no signals: {skipped}")

        if not dry_run:
            session.commit()
            typer.echo("All signals persisted")
        else:
            typer.echo("DRY RUN: scores computed but not persisted")


@score_app.command(name="composite")
def composite(
    ticker: str = typer.Option(None, "--ticker", help="Company ticker to score"),
    all_companies: bool = typer.Option(False, "--all", help="Score all active companies"),
    scoring_date: str = typer.Option(
        None, "--date", help="Scoring date (YYYY-MM-DD), defaults to today"
    ),
):
    """Compute composite scores and persist DailyScore rows."""
    from datetime import date as date_type

    from sqlalchemy import select

    from ai_washer.analysis.scoring_orchestrator import ScoringOrchestrator
    from ai_washer.config import load_app_settings, load_scoring_config
    from ai_washer.db.models import Company
    from ai_washer.db.session import create_engine_from_settings, get_session_factory

    if not ticker and not all_companies:
        typer.echo("Provide --ticker or --all", err=True)
        raise typer.Exit(code=1)

    app_settings = load_app_settings()
    scoring_cfg = load_scoring_config()
    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)

    parsed_date = date_type.fromisoformat(scoring_date) if scoring_date is not None else None

    with session_factory() as session:
        orch = ScoringOrchestrator(
            session=session,
            config=scoring_cfg,
            scoring_date=parsed_date,
        )

        if all_companies:
            all_results = orch.score_all()

            total = len(all_results)
            composites = sum(1 for _, r in all_results if r)
            typer.echo(f"\nCompanies scored: {total}")
            typer.echo(f"Composites produced: {composites}")
            session.commit()
            typer.echo("All composite scores persisted")
        else:
            stmt = select(Company).where(Company.ticker == ticker.upper())
            company = session.execute(stmt).scalar_one_or_none()

            if company is None:
                typer.echo(f"Company not found: {ticker}", err=True)
                raise typer.Exit(code=1)

            results = orch.score_company(company.id, company.ticker)
            orch.persist_signals(company.id, results)
            composite_result = orch.compute_and_persist_composite(company.id, results)

            if composite_result is None:
                typer.echo("No composite score produced (insufficient signals)")
            else:
                typer.echo(f"Ticker:     {company.ticker}")
                typer.echo(f"Composite:  {composite_result.score}")
                typer.echo(f"Risk Band:  {composite_result.risk_band}")
                typer.echo(f"Confidence: {composite_result.confidence:.2f}")
                typer.echo(f"Breakdown:  {composite_result.signal_breakdown}")

            session.commit()
            typer.echo("Scores persisted")


# ---------------------------------------------------------------------------
# patent subcommands
# ---------------------------------------------------------------------------


@patent_app.command(name="collect")
def patent_collect_cmd(
    identifier: str = typer.Argument(help="Company ticker or CIK"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen"),
):
    """Collect AI-related patents for a single company from PatentsView."""
    from sqlalchemy import select

    from ai_washer.config import load_app_settings
    from ai_washer.db.models import Company
    from ai_washer.db.session import create_engine_from_settings, get_session_factory
    from ai_washer.ingestion.patent_collector import PatentCollector

    app_settings = load_app_settings()
    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        stmt = select(Company).where(
            (Company.ticker == identifier.upper()) | (Company.cik == identifier)
        )
        company = session.execute(stmt).scalar_one_or_none()
        if company is None:
            typer.echo(f"Company not found: {identifier}", err=True)
            raise typer.Exit(code=1)
        # Capture values before session closes
        company_id, company_name, aliases = company.id, company.name, company.aliases

    if dry_run:
        typer.echo(f"DRY RUN: Would collect patents for {company_name}")
        return

    collector = PatentCollector(app_settings=app_settings)
    result = collector.collect_for_company(company_id, company_name, aliases)
    typer.echo(f"Patents collected: {result.patent_count}")
    typer.echo(f"Skipped (already stored): {result.skipped_count}")
    if result.errors:
        for err in result.errors:
            typer.echo(f"  Error: {err}", err=True)


@patent_app.command(name="collect-all")
def patent_collect_all_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen"),
):
    """Collect AI-related patents for all active companies."""
    from ai_washer.config import load_app_settings
    from ai_washer.ingestion.patent_collector import PatentCollector

    app_settings = load_app_settings()

    if dry_run:
        from sqlalchemy import func, select

        from ai_washer.db.models import Company
        from ai_washer.db.session import create_engine_from_settings, get_session_factory

        engine = create_engine_from_settings(app_settings)
        sf = get_session_factory(engine)
        with sf() as session:
            count = session.execute(
                select(func.count()).where(
                    Company.is_active == True,  # noqa: E712
                    Company.cik.isnot(None),
                )
            ).scalar()
        typer.echo(f"DRY RUN: Would collect patents for {count} active companies")
        return

    collector = PatentCollector(app_settings=app_settings)
    results = collector.collect_all()
    total = sum(r.patent_count for r in results)
    skipped = sum(r.skipped_count for r in results)
    errors = sum(len(r.errors) for r in results)
    typer.echo(f"Collection complete for {len(results)} companies")
    typer.echo(f"Total patents: {total}")
    typer.echo(f"Total skipped: {skipped}")
    if errors:
        typer.echo(f"Total errors: {errors}")


# ---------------------------------------------------------------------------
# github subcommands
# ---------------------------------------------------------------------------


@github_app.command(name="collect")
def github_collect_cmd(
    identifier: str = typer.Argument(help="Company ticker or CIK"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen"),
):
    """Collect GitHub repository data for a single company."""
    from sqlalchemy import select

    from ai_washer.config import load_app_settings
    from ai_washer.db.models import Company
    from ai_washer.db.session import create_engine_from_settings, get_session_factory
    from ai_washer.ingestion.github_collector import GitHubCollector

    app_settings = load_app_settings()
    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        stmt = select(Company).where(
            (Company.ticker == identifier.upper()) | (Company.cik == identifier)
        )
        company = session.execute(stmt).scalar_one_or_none()
        if company is None:
            typer.echo(f"Company not found: {identifier}", err=True)
            raise typer.Exit(code=1)
        # Capture values before session closes
        company_id = company.id
        company_name = company.name
        github_org = (company.aliases or {}).get("github_org")

    if dry_run:
        typer.echo(f"DRY RUN: Would collect GitHub data for {company_name}")
        typer.echo(f"GitHub org: {github_org or '(none)'}")
        return

    collector = GitHubCollector(app_settings=app_settings)
    result = collector.collect_for_company(company_id, github_org)
    typer.echo(f"Repos collected: {result.repo_count}")
    typer.echo(f"Skipped (already stored): {result.skipped_count}")
    if result.errors:
        for err in result.errors:
            typer.echo(f"  Error: {err}", err=True)


@github_app.command(name="collect-all")
def github_collect_all_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen"),
):
    """Collect GitHub repository data for all active companies."""
    from ai_washer.config import load_app_settings
    from ai_washer.ingestion.github_collector import GitHubCollector

    app_settings = load_app_settings()

    if dry_run:
        from sqlalchemy import func, select

        from ai_washer.db.models import Company
        from ai_washer.db.session import create_engine_from_settings, get_session_factory

        engine = create_engine_from_settings(app_settings)
        sf = get_session_factory(engine)
        with sf() as session:
            count = session.execute(
                select(func.count()).where(
                    Company.is_active == True,  # noqa: E712
                    Company.cik.isnot(None),
                )
            ).scalar()
        typer.echo(f"DRY RUN: Would collect GitHub data for {count} active companies")
        return

    collector = GitHubCollector(app_settings=app_settings)
    results = collector.collect_all()
    total = sum(r.repo_count for r in results)
    skipped = sum(r.skipped_count for r in results)
    errors = sum(len(r.errors) for r in results)
    typer.echo(f"Collection complete for {len(results)} companies")
    typer.echo(f"Total repos: {total}")
    typer.echo(f"Total skipped: {skipped}")
    if errors:
        typer.echo(f"Total errors: {errors}")


# ---------------------------------------------------------------------------
# earnings subcommands
# ---------------------------------------------------------------------------


@earnings_app.command(name="company")
def earnings_collect_company_cmd(
    identifier: str = typer.Argument(help="Company ticker or CIK"),
    quarters: int = typer.Option(8, "--quarters", help="Number of quarters to collect"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen"),
):
    """Collect earnings call transcripts for a single company."""
    from sqlalchemy import select

    from ai_washer.config import load_app_settings
    from ai_washer.db.models import Company
    from ai_washer.db.session import create_engine_from_settings, get_session_factory

    app_settings = load_app_settings()
    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        stmt = select(Company).where(
            (Company.ticker == identifier.upper()) | (Company.cik == identifier)
        )
        company = session.execute(stmt).scalar_one_or_none()
        if company is None:
            typer.echo(f"Company not found: {identifier}", err=True)
            raise typer.Exit(code=1)
        company_id = company.id
        company_ticker = company.ticker

    if dry_run:
        typer.echo(f"DRY RUN: Would collect {quarters} quarters of earnings for {company_ticker}")
        return

    from ai_washer.ingestion.earnings_collector import EarningsCollector

    collector = EarningsCollector(app_settings=app_settings)
    result = collector.collect_for_company(company_id, company_ticker, num_quarters=quarters)
    typer.echo(f"Transcripts collected: {result.transcript_count}")
    typer.echo(f"Skipped (already stored): {result.skipped_count}")
    if result.errors:
        for err in result.errors:
            typer.echo(f"  Error: {err}", err=True)


@earnings_app.command(name="all")
def earnings_collect_all_cmd(
    quarters: int = typer.Option(8, "--quarters", help="Number of quarters to collect"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen"),
):
    """Collect earnings call transcripts for all active companies."""
    from ai_washer.config import load_app_settings

    app_settings = load_app_settings()

    if dry_run:
        from sqlalchemy import func, select

        from ai_washer.db.models import Company
        from ai_washer.db.session import create_engine_from_settings, get_session_factory

        engine = create_engine_from_settings(app_settings)
        sf = get_session_factory(engine)
        with sf() as session:
            count = session.execute(
                select(func.count()).where(
                    Company.is_active == True,  # noqa: E712
                    Company.cik.isnot(None),
                )
            ).scalar()
        typer.echo(f"DRY RUN: Would collect {quarters} quarters of earnings for {count} companies")
        return

    from ai_washer.ingestion.earnings_collector import EarningsCollector

    collector = EarningsCollector(app_settings=app_settings)
    results = collector.collect_all()
    total = sum(r.transcript_count for r in results)
    skipped = sum(r.skipped_count for r in results)
    errors = sum(len(r.errors) for r in results)
    typer.echo(f"Collection complete for {len(results)} companies")
    typer.echo(f"Total transcripts: {total}")
    typer.echo(f"Total skipped: {skipped}")
    if errors:
        typer.echo(f"Total errors: {errors}")


# ---------------------------------------------------------------------------
# job subcommands
# ---------------------------------------------------------------------------


@job_app.command(name="collect")
def job_collect_cmd(
    identifier: str = typer.Argument(help="Company ticker or CIK"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen"),
):
    """Collect job postings for a single company."""
    from sqlalchemy import select

    from ai_washer.config import load_app_settings
    from ai_washer.db.models import Company
    from ai_washer.db.session import create_engine_from_settings, get_session_factory

    app_settings = load_app_settings()
    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        stmt = select(Company).where(
            (Company.ticker == identifier.upper()) | (Company.cik == identifier)
        )
        company = session.execute(stmt).scalar_one_or_none()
        if company is None:
            typer.echo(f"Company not found: {identifier}", err=True)
            raise typer.Exit(code=1)
        company_id = company.id
        company_name = company.name
        company_cik = company.cik or ""

    if dry_run:
        typer.echo(f"DRY RUN: Would collect job postings for {company_name}")
        return

    from ai_washer.ingestion.job_collector import JobCollector

    collector = JobCollector(app_settings=app_settings)
    result = collector.collect_for_company(company_id, company_name, company_cik)
    typer.echo(f"Jobs found: {result.jobs_found}")
    typer.echo(f"New postings: {result.jobs_new}")
    typer.echo(f"Updated postings: {result.jobs_updated}")
    if result.errors:
        for err in result.errors:
            typer.echo(f"  Error: {err}", err=True)


@job_app.command(name="collect-all")
def job_collect_all_cmd(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen"),
):
    """Collect job postings for all active companies."""
    from ai_washer.config import load_app_settings

    app_settings = load_app_settings()

    if dry_run:
        from sqlalchemy import func, select

        from ai_washer.db.models import Company
        from ai_washer.db.session import create_engine_from_settings, get_session_factory

        engine = create_engine_from_settings(app_settings)
        sf = get_session_factory(engine)
        with sf() as session:
            count = session.execute(
                select(func.count()).where(
                    Company.is_active == True,  # noqa: E712
                    Company.cik.isnot(None),
                )
            ).scalar()
        typer.echo(f"DRY RUN: Would collect job postings for {count} active companies")
        return

    from ai_washer.ingestion.job_collector import JobCollector

    collector = JobCollector(app_settings=app_settings)
    results = collector.collect_all()
    total_found = sum(r.jobs_found for r in results)
    total_new = sum(r.jobs_new for r in results)
    total_updated = sum(r.jobs_updated for r in results)
    total_errors = sum(len(r.errors) for r in results)
    typer.echo(f"Collection complete for {len(results)} companies")
    typer.echo(f"Total jobs found: {total_found}")
    typer.echo(f"Total new: {total_new}")
    typer.echo(f"Total updated: {total_updated}")
    if total_errors:
        typer.echo(f"Total errors: {total_errors}")


# ---------------------------------------------------------------------------
# pipeline subcommands
# ---------------------------------------------------------------------------


@pipeline_app.command(name="run")
def pipeline_run_cmd():
    """Run the full daily pipeline: ingest all sources, score, compute composites."""
    from ai_washer.pipeline.daily_flow import daily_pipeline_flow

    result = daily_pipeline_flow()

    typer.echo(f"\nPipeline status: {result.status}")
    typer.echo(f"Companies processed: {result.companies_processed}")
    typer.echo(f"Total errors: {result.total_errors}")
    typer.echo(f"Stages: {len(result.stages)}")
    for stage in result.stages:
        marker = "OK" if stage.status == "succeeded" else stage.status.upper()
        typer.echo(f"  [{marker}] {stage.stage} ({stage.companies_processed} companies)")
        for err in stage.errors:
            typer.echo(f"       Error: {err}", err=True)


@pipeline_app.command(name="status")
def pipeline_status_cmd(
    limit: int = typer.Option(5, "--limit", help="Number of recent runs to show"),
):
    """Show recent pipeline run results."""
    from sqlalchemy import select

    from ai_washer.config import load_app_settings
    from ai_washer.db.models import PipelineRun
    from ai_washer.db.session import create_engine_from_settings, get_session_factory

    settings = load_app_settings()
    engine = create_engine_from_settings(settings)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        stmt = (
            select(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .limit(limit)
        )
        runs = session.execute(stmt).scalars().all()

        if not runs:
            typer.echo("No pipeline runs found.")
            return

        typer.echo(
            f"{'Run ID':<12} {'Started':<20} {'Ended':<20} "
            f"{'Status':<18} {'Companies':<12} {'Errors'}"
        )
        typer.echo("-" * 100)
        for run in runs:
            short_id = str(run.id)[:8]
            started = str(run.started_at)[:19] if run.started_at else "N/A"
            ended = str(run.ended_at)[:19] if run.ended_at else "running"
            error_count = len(run.errors) if isinstance(run.errors, list) else 0
            typer.echo(
                f"{short_id:<12} {started:<20} {ended:<20} "
                f"{run.status:<18} {run.companies_processed:<12} {error_count}"
            )


@pipeline_app.command(name="staleness")
def pipeline_staleness_cmd():
    """Show data source staleness status."""
    from ai_washer.config import load_app_settings
    from ai_washer.db.session import create_engine_from_settings, get_session_factory
    from ai_washer.pipeline.monitoring import check_staleness, get_all_source_status

    settings = load_app_settings()
    engine = create_engine_from_settings(settings)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        sources = get_all_source_status(session)
        stale_reports = check_staleness(session)
        session.commit()

        stale_names = {r.source_name for r in stale_reports}

        if not sources:
            typer.echo("No data sources configured.")
            return

        typer.echo(
            f"{'Source':<20} {'Last Success':<22} "
            f"{'Cadence (h)':<14} {'Stale?':<8} {'Last Error'}"
        )
        typer.echo("-" * 100)
        for src in sources:
            last_ok = str(src.last_success_at)[:19] if src.last_success_at else "never"
            is_stale = "YES" if src.source_name in stale_names else "no"
            last_err = (src.last_error_message or "")[:30]
            typer.echo(
                f"{src.source_name:<20} {last_ok:<22} "
                f"{src.expected_cadence_hours:<14} {is_stale:<8} {last_err}"
            )
