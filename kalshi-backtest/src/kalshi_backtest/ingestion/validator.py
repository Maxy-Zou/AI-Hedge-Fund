"""DataValidator: post-ingestion data quality checks using DuckDB window functions.

Outputs a ValidationReport with:
- coverage_pct: percentage of expected trading days that have candle data
- gap_count: number of gaps > 1 day between consecutive candles (per ticker)
- anomaly_count: candles with prices outside valid range (0-100 cents)
- summary: Rich table printed to console after each run

Gap detection uses DuckDB LAG() window function — faster than Python loops
for millions of candle rows (see RESEARCH.md DuckDB gap detection query).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import duckdb
import structlog
from rich.console import Console
from rich.table import Table


logger = structlog.get_logger(__name__)
_console = Console()

_GAP_QUERY = """
WITH daily AS (
    SELECT ticker, ts,
           LAG(ts) OVER (PARTITION BY ticker ORDER BY ts) AS prev_ts
    FROM candles
    WHERE ticker = ?
),
gaps AS (
    SELECT ticker, ts, prev_ts,
           DATE_DIFF('day', prev_ts, ts) AS gap_days
    FROM daily
    WHERE DATE_DIFF('day', prev_ts, ts) > 1
)
SELECT ticker, prev_ts AS gap_start, ts AS gap_end, gap_days
FROM gaps
ORDER BY gap_days DESC
"""

_COVERAGE_QUERY = """
SELECT
    COUNT(*) AS total_candles,
    MIN(ts) AS earliest_ts,
    MAX(ts) AS latest_ts,
    DATE_DIFF('day', MIN(ts), MAX(ts)) + 1 AS expected_days
FROM candles
WHERE ticker = ?
"""

_ANOMALY_QUERY = """
SELECT COUNT(*) AS anomaly_count
FROM candles
WHERE ticker = ?
  AND (close_price < 0 OR close_price > 100)
"""


@dataclass
class GapRecord:
    """A detected gap between two consecutive candle timestamps."""

    ticker: str
    gap_start: datetime
    gap_end: datetime
    gap_days: int


@dataclass
class ValidationReport:
    """Summary of data quality for a single market ticker.

    Attributes:
        ticker: Market ticker checked.
        total_candles: Number of candle rows in the database.
        coverage_pct: Ratio of candles to expected trading days (0.0–100.0).
        gap_count: Number of date gaps > 1 day.
        anomaly_count: Number of candles with prices outside 0-100 cents.
        gaps: Details of each gap found.
    """

    ticker: str
    total_candles: int = 0
    coverage_pct: float = 0.0
    gap_count: int = 0
    anomaly_count: int = 0
    gaps: list[GapRecord] = field(default_factory=list)


class DataValidator:
    """Validates data completeness and quality after ingestion.

    Uses DuckDB window functions for gap detection — significantly faster
    than Python iteration for large candle tables.

    Args:
        con: Open DuckDB connection with the Phase 1 schema applied.
    """

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def validate_ticker(self, ticker: str) -> ValidationReport:
        """Run all quality checks for a single market ticker.

        Args:
            ticker: Market ticker to validate.

        Returns:
            ValidationReport with coverage, gap, and anomaly stats.
        """
        report = ValidationReport(ticker=ticker)

        # Coverage stats
        cov_row = self._con.execute(_COVERAGE_QUERY, [ticker]).fetchone()
        if cov_row and cov_row[0] > 0:
            total_candles, earliest, latest, expected_days = cov_row
            report.total_candles = int(total_candles)
            if expected_days and expected_days > 0:
                report.coverage_pct = round(100.0 * total_candles / expected_days, 1)

        # Gap detection
        gap_rows = self._con.execute(_GAP_QUERY, [ticker]).fetchall()
        report.gaps = [
            GapRecord(
                ticker=row[0],
                gap_start=row[1],
                gap_end=row[2],
                gap_days=int(row[3]),
            )
            for row in gap_rows
        ]
        report.gap_count = len(report.gaps)

        # Anomaly detection
        anom_row = self._con.execute(_ANOMALY_QUERY, [ticker]).fetchone()
        report.anomaly_count = int(anom_row[0]) if anom_row else 0

        return report

    def validate_all(self, tickers: list[str]) -> list[ValidationReport]:
        """Validate all tickers and print a summary Rich table.

        Args:
            tickers: List of market tickers to validate.

        Returns:
            List of ValidationReport, one per ticker.
        """
        reports = [self.validate_ticker(t) for t in tickers]
        self._print_report(reports)
        return reports

    def _print_report(self, reports: list[ValidationReport]) -> None:
        """Print a Rich table summarizing all ValidationReports."""
        table = Table(title="Kalshi Ingestion Validation Report", show_header=True)
        table.add_column("Ticker", style="cyan", no_wrap=True)
        table.add_column("Candles", justify="right")
        table.add_column("Coverage %", justify="right")
        table.add_column("Gaps", justify="right", style="yellow")
        table.add_column("Anomalies", justify="right", style="red")

        for r in reports:
            gap_style = "red" if r.gap_count > 0 else "green"
            anom_style = "red" if r.anomaly_count > 0 else "green"
            table.add_row(
                r.ticker,
                str(r.total_candles),
                f"{r.coverage_pct:.1f}%",
                f"[{gap_style}]{r.gap_count}[/{gap_style}]",
                f"[{anom_style}]{r.anomaly_count}[/{anom_style}]",
            )

        _console.print(table)
        logger.info(
            "validation_report_printed",
            ticker_count=len(reports),
            total_gaps=sum(r.gap_count for r in reports),
            total_anomalies=sum(r.anomaly_count for r in reports),
        )
