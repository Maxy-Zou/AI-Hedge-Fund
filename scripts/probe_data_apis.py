"""Vendor-API drift probe — lightweight canary for edgartools, yfinance, Finnhub, FRED.

Runs each external data-source API once with a known-good ticker/series
and asserts the response shape our code depends on. No DB, no LLM calls,
no cost. Intended for a weekly remote agent that opens a GitHub issue
when any probe fails.

Environment:
    EDGAR_IDENTITY    (required)  e.g. "YourName you@example.com"
    FINNHUB_API_KEY   (required)  free tier, 60 req/min
    FRED_API_KEY      (required)  free

Exit codes:
    0  all probes passed
    1  one or more probes failed (details on stdout + stderr)

Usage:
    uv run python scripts/probe_data_apis.py
"""

from __future__ import annotations

import os
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

# NOTE: imports inside each probe so a single broken library doesn't
# short-circuit the whole script at module-load time.


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    detail: str


def _require_env(var: str) -> str:
    value = os.environ.get(var, "").strip()
    if not value:
        msg = f"{var} not set"
        raise RuntimeError(msg)
    return value


def probe_edgartools_filing() -> str:
    """EntityFiling.form must exist and equal '10-K' for AAPL's latest 10-K."""
    import edgar

    edgar.set_identity(_require_env("EDGAR_IDENTITY"))
    filings = edgar.Company("AAPL").get_filings(form="10-K")
    latest = filings.latest(1)
    if isinstance(latest, list):
        latest = latest[0]
    if not hasattr(latest, "form"):
        attrs = sorted(a for a in dir(latest) if not a.startswith("_"))[:10]
        msg = f"EntityFiling missing .form attribute; has: {attrs}"
        raise AssertionError(msg)
    if latest.form != "10-K":
        msg = f"expected form='10-K', got {latest.form!r}"
        raise AssertionError(msg)
    return f"EntityFiling.form = {latest.form!r} (accession {latest.accession_no})"


def probe_edgartools_facts() -> str:
    """EntityFacts.to_dataframe(pit_mode=True) must expose pit_mode columns."""
    import edgar

    edgar.set_identity(_require_env("EDGAR_IDENTITY"))
    facts = edgar.Company("AAPL").get_facts()
    if not hasattr(facts, "to_dataframe"):
        msg = "EntityFacts missing .to_dataframe (API drift — was .to_pandas in pre-5.x)"
        raise AssertionError(msg)
    df = facts.to_dataframe(pit_mode=True)
    required = {
        "concept",
        "value",
        "numeric_value",
        "unit",
        "period_end",
        "fiscal_year",
        "fiscal_period",
        "filing_date",
        "form_type",
    }
    missing = required - set(df.columns)
    if missing:
        msg = f"pit_mode columns missing: {sorted(missing)}; got: {sorted(df.columns)}"
        raise AssertionError(msg)
    if len(df) < 100:
        msg = f"pit_mode DataFrame suspiciously small: {len(df)} rows"
        raise AssertionError(msg)
    return f"pit_mode DataFrame: {len(df)} rows, {len(df.columns)} cols"


def probe_yfinance() -> str:
    """yfinance.download must return non-empty OHLCV for a recent 5-business-day window."""
    import yfinance as yf

    end = date.today()
    start = end - timedelta(days=14)  # covers a ≥5bd window even across weekends/holidays
    df = yf.download(
        "AAPL",
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=False,
        progress=False,
    )
    if df.empty:
        msg = "yfinance returned empty DataFrame for AAPL"
        raise AssertionError(msg)
    required = {"Open", "High", "Low", "Close", "Volume"}
    cols = df.columns.get_level_values(0) if df.columns.nlevels > 1 else df.columns
    missing = required - set(cols)
    if missing:
        msg = f"yfinance columns missing: {sorted(missing)}; got: {list(cols)}"
        raise AssertionError(msg)
    close = df["Close"]
    last_close = float(close.iloc[-1]) if close.ndim == 1 else float(close.iloc[-1, 0])
    return f"yfinance: {len(df)} bars, last close={last_close:.2f}"


def probe_finnhub() -> str:
    """Finnhub company-news must return a list with dict items carrying headline+datetime."""
    import finnhub

    client = finnhub.Client(api_key=_require_env("FINNHUB_API_KEY"))
    end = date.today()
    start = end - timedelta(days=7)
    items = client.company_news("AAPL", _from=start.isoformat(), to=end.isoformat())
    if not isinstance(items, list):
        msg = f"Finnhub company_news returned {type(items).__name__}, expected list"
        raise AssertionError(msg)
    if not items:
        msg = "Finnhub company_news returned empty list for AAPL over last 7 days"
        raise AssertionError(msg)
    sample = items[0]
    required = {"headline", "datetime"}
    missing = required - set(sample.keys())
    if missing:
        msg = f"Finnhub news item missing keys: {sorted(missing)}; got: {sorted(sample.keys())}"
        raise AssertionError(msg)
    head_len = len(sample["headline"])
    return f"Finnhub company_news: {len(items)} items, latest headline len={head_len}"


def probe_fred() -> str:
    """FRED series GET must return a pandas Series for a stable series id."""
    from fredapi import Fred

    fred = Fred(api_key=_require_env("FRED_API_KEY"))
    series = fred.get_series("GDP")  # nominal GDP, quarterly, never renamed
    if series is None or len(series) == 0:
        msg = "FRED series GDP returned empty"
        raise AssertionError(msg)
    latest_idx = series.index.max()
    latest_val = float(series.iloc[-1])
    return f"FRED GDP: {len(series)} obs, latest={latest_val:.2f} ({latest_idx.date()})"


PROBES: list[tuple[str, Callable[[], str]]] = [
    ("edgartools.EntityFiling.form", probe_edgartools_filing),
    ("edgartools.EntityFacts.to_dataframe(pit_mode=True)", probe_edgartools_facts),
    ("yfinance.download OHLCV", probe_yfinance),
    ("finnhub.company_news", probe_finnhub),
    ("fredapi.Fred.get_series", probe_fred),
]


def run_all() -> list[ProbeResult]:
    results: list[ProbeResult] = []
    for name, fn in PROBES:
        try:
            detail = fn()
            results.append(ProbeResult(name=name, ok=True, detail=detail))
        except Exception as exc:  # noqa: BLE001 -- probe boundary; any failure is a drift signal
            tb = traceback.format_exc(limit=4)
            results.append(
                ProbeResult(
                    name=name,
                    ok=False,
                    detail=f"{type(exc).__name__}: {exc}\n{tb}",
                )
            )
    return results


def format_report(results: list[ProbeResult]) -> str:
    lines = ["# Vendor-API Drift Probe", ""]
    passed = sum(1 for r in results if r.ok)
    total = len(results)
    lines.append(f"**Result: {passed}/{total} probes passed**")
    lines.append("")
    for r in results:
        marker = "PASS" if r.ok else "FAIL"
        lines.append(f"## [{marker}] {r.name}")
        lines.append("")
        if r.ok:
            lines.append(f"    {r.detail}")
        else:
            lines.append("```")
            lines.append(r.detail.rstrip())
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    results = run_all()
    report = format_report(results)
    print(report)
    all_ok = all(r.ok for r in results)
    if not all_ok:
        failed = [r.name for r in results if not r.ok]
        print(f"FAILED probes: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
