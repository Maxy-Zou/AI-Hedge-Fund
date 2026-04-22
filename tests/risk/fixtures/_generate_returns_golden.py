"""One-shot generator for ``returns_golden.csv``.

Produces a deterministic 252-trading-day log-return CSV for six tickers
(AAPL, MSFT, JNJ, JPM, PG, NEW). MSFT is constructed to correlate ~0.95
with AAPL so the correlation test has a known top-correlated pair. NEW is
truncated to only 30 rows so the drawdown / correlation checks can exercise
their "insufficient history" branches.

The CSV is committed to the repo; this script is kept for regeneration if
the fixture ever needs new tickers or a longer window. It is NOT run during
tests.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np

OUT_PATH = Path(__file__).parent / "returns_golden.csv"

TRADING_DAYS = 252
START_DATE = date(2024, 1, 2)  # Tuesday (2024-01-01 was a holiday)

TICKERS: list[str] = ["AAPL", "MSFT", "JNJ", "JPM", "PG", "NEW"]


def _business_days(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def generate() -> None:
    rng = np.random.default_rng(seed=42)

    drift = 0.0005
    std = 0.015

    # Independent Gaussian returns for 5 tickers
    indep_returns: dict[str, np.ndarray] = {}
    for ticker in ("AAPL", "JNJ", "JPM", "PG", "NEW"):
        indep_returns[ticker] = rng.normal(drift, std, size=TRADING_DAYS)

    # MSFT correlated ~0.95 with AAPL by construction
    noise = rng.normal(0.0, std, size=TRADING_DAYS)
    msft = 0.95 * indep_returns["AAPL"] + np.sqrt(1 - 0.95**2) * noise
    # Re-centre MSFT to match the same drift/std profile approximately
    msft = msft - msft.mean() + drift

    returns_by_ticker: dict[str, np.ndarray] = {
        "AAPL": indep_returns["AAPL"],
        "MSFT": msft,
        "JNJ": indep_returns["JNJ"],
        "JPM": indep_returns["JPM"],
        "PG": indep_returns["PG"],
        "NEW": indep_returns["NEW"][:30],  # deliberately short history
    }

    dates = _business_days(START_DATE, TRADING_DAYS)

    with OUT_PATH.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", *TICKERS])
        for i, d in enumerate(dates):
            row: list[str] = [d.isoformat()]
            for ticker in TICKERS:
                series = returns_by_ticker[ticker]
                row.append(f"{series[i]:.8f}" if i < len(series) else "")
            writer.writerow(row)

    print(f"Wrote {OUT_PATH} with {TRADING_DAYS} rows and {len(TICKERS)} ticker columns.")


if __name__ == "__main__":
    generate()
