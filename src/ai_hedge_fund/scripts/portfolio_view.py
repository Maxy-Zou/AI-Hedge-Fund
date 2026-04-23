"""Render the ranked portfolio view (Phase 8 SIG-02).

Reads ``record_type='analysis'`` rows from ``episodic_memory``, groups by
sector, ranks by conviction DESC + as_of_date DESC. No caching -- the
append-only DB is the truth (Pitfall C / T-08-15).

Usage::

    uv run python -m ai_hedge_fund.scripts.portfolio_view \\
        --as-of 2026-04-20 [--sector Technology] [--limit 50] [--json]

First compliance-grade operator view over completed analyses. The CLI
wraps :func:`ai_hedge_fund.output.portfolio_view.query_portfolio_view`
(Plan 08-02) -- zero new business logic here.

Threat mitigations (see 08-04-PLAN.md::threat_model):
    T-08-20 (DoS): the underlying query caps at ``limit_per_sector``
            (default 50); the CLI exposes the cap via ``--limit``.
    T-08-31 (Information disclosure): v1 accepts full thesis rendering
            to stdout; operator controls the terminal.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import structlog
from sqlalchemy.orm import Session

from ai_hedge_fund.output.portfolio_view import query_portfolio_view

logger = structlog.get_logger(__name__)


def _format_markdown(view: dict[str, list[dict[str, Any]]]) -> str:
    """Render the sector-keyed view as a compact markdown report.

    Empty view -> ``(no signals)`` (friendly operator message, never a
    traceback). Non-empty view -> sorted sector headers with ticker-level
    bullets; thesis summaries are clipped to 120 chars.
    """
    if not view:
        return "# Portfolio View\n\n(no signals)\n"
    lines: list[str] = ["# Portfolio View", ""]
    for sector in sorted(view.keys()):
        entries = view[sector]
        lines.append(f"## {sector} ({len(entries)})")
        lines.append("")
        for e in entries:
            conv = e.get("conviction", "-")
            direction = e.get("direction", "-")
            as_of = e.get("as_of_date", "-")
            thesis = (e.get("thesis_summary") or "").strip()
            if len(thesis) > 120:
                thesis = thesis[:117] + "..."
            lines.append(
                f"- **{e.get('ticker', '-')}** [{direction}] "
                f"conviction {conv}/100 "
                f"(as_of {as_of}, episodic://{e.get('episodic_id', '-')})"
            )
            if thesis:
                lines.append(f"    - {thesis}")
        lines.append("")
    return "\n".join(lines)


def _run(
    session: Session,
    *,
    as_of_date: str,
    sector: str | None,
    limit_per_sector: int,
    as_json: bool,
) -> str:
    """Query the portfolio view and render it as markdown or JSON.

    Separated from :func:`_main` so tests can drive the rendering path
    with a seeded session without going through argparse + DB bootstrap.
    """
    view = query_portfolio_view(
        session,
        as_of_date=as_of_date,
        sector=sector,
        limit_per_sector=limit_per_sector,
    )
    if as_json:
        return json.dumps(view, indent=2, default=str)
    return _format_markdown(view)


def _main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m ai_hedge_fund.scripts.portfolio_view``.

    Parses ``--as-of`` (required) + optional ``--sector`` / ``--limit`` /
    ``--json`` / ``--database-url``; opens a session; prints the rendered
    view. Returns ``0`` on success, ``1`` on any unhandled exception.
    """
    from ai_hedge_fund.config import AppSettings
    from ai_hedge_fund.db import session as session_mod

    parser = argparse.ArgumentParser(
        description="Render the ranked portfolio view (Phase 8 SIG-02).",
    )
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--sector", default=None)
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        dest="limit_per_sector",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Override DATABASE_URL from env",
    )
    args = parser.parse_args(argv)

    settings = AppSettings()
    url = args.database_url or settings.database_url
    engine = session_mod.get_engine(url)
    factory = session_mod.get_session_factory(engine)
    session = factory()
    try:
        try:
            out = _run(
                session,
                as_of_date=args.as_of,
                sector=args.sector,
                limit_per_sector=args.limit_per_sector,
                as_json=args.as_json,
            )
        except Exception as exc:  # noqa: BLE001 -- CLI boundary
            print(f"ERROR: {exc}", file=sys.stderr)
            logger.error("portfolio_view_failed", error=str(exc))
            return 1
        print(out)
        return 0
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(_main())
