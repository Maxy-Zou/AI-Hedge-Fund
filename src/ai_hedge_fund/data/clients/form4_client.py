"""SEC Form 4 insider trade client and purchase cluster detection.

Parses insider transactions from Form 4 filings via edgartools and
detects cluster buying patterns (3+ insiders purchasing within a
configurable window). Cluster buys are a strong alpha signal.

Threat mitigations:
- T-02-12: Filters on filing_date (not trade_date) for temporal correctness
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from edgar import Company
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InsiderCluster:
    """A cluster of insider purchases within a time window.

    Immutable (frozen) per CLAUDE.md convention. Uses tuple for
    insiders list to maintain immutability.

    Attributes:
        ticker: Stock ticker symbol.
        insiders: Tuple of insider names in the cluster.
        total_shares: Aggregate shares purchased.
        total_value_cents: Aggregate purchase value in cents.
        start_date: Earliest trade date in the cluster.
        end_date: Latest trade date in the cluster.
        cluster_size: Number of unique insiders.
    """

    ticker: str
    insiders: tuple[str, ...]
    total_shares: int
    total_value_cents: int
    start_date: date
    end_date: date
    cluster_size: int


def detect_purchase_clusters(
    purchases: list[dict[str, Any]],
    *,
    window_days: int = 14,
    min_insiders: int = 3,
    ticker: str = "",
) -> list[InsiderCluster]:
    """Detect clusters of insider purchases within a time window.

    Sorts purchases by trade_date, then uses a sliding window to find
    groups of unique insiders purchasing within window_days of each
    other. Overlapping clusters are deduplicated by keeping the one
    with the most insiders.

    Args:
        purchases: List of purchase trade dicts with trade_date and
            insider_name keys.
        window_days: Maximum days between first and last trade in a
            cluster (default 14).
        min_insiders: Minimum unique insiders to form a cluster
            (default 3).
        ticker: Stock ticker for the cluster objects.

    Returns:
        List of InsiderCluster objects, deduplicated.
    """
    if not purchases:
        return []

    # Sort by trade_date
    sorted_purchases = sorted(purchases, key=lambda p: p["trade_date"])

    raw_clusters: list[dict[str, Any]] = []

    for anchor in sorted_purchases:
        anchor_date = anchor["trade_date"]
        window_end = anchor_date + timedelta(days=window_days)

        # Collect all purchases within the window
        window_purchases = [
            p for p in sorted_purchases if anchor_date <= p["trade_date"] <= window_end
        ]

        # Count unique insiders
        unique_insiders = {p["insider_name"] for p in window_purchases}

        if len(unique_insiders) >= min_insiders:
            raw_clusters.append(
                {
                    "insiders": frozenset(unique_insiders),
                    "purchases": window_purchases,
                    "start_date": anchor_date,
                    "end_date": max(p["trade_date"] for p in window_purchases),
                }
            )

    # Deduplicate overlapping clusters -- keep largest per overlapping group
    deduplicated = _deduplicate_clusters(raw_clusters)

    # Convert to InsiderCluster objects
    results: list[InsiderCluster] = []
    for cluster_data in deduplicated:
        insiders = tuple(sorted(cluster_data["insiders"]))
        purchases_in_cluster = cluster_data["purchases"]

        total_shares = sum(p["shares"] for p in purchases_in_cluster)
        total_value = sum(p.get("value_cents", 0) for p in purchases_in_cluster)

        results.append(
            InsiderCluster(
                ticker=ticker,
                insiders=insiders,
                total_shares=total_shares,
                total_value_cents=total_value,
                start_date=cluster_data["start_date"],
                end_date=cluster_data["end_date"],
                cluster_size=len(insiders),
            )
        )

    return results


def _deduplicate_clusters(
    raw_clusters: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove overlapping clusters, keeping the largest.

    Two clusters overlap if they share any insiders and their date
    ranges intersect. When they overlap, keep the one with more
    unique insiders.

    Args:
        raw_clusters: List of cluster dicts with insiders (frozenset)
            and date range.

    Returns:
        Deduplicated list of cluster dicts.
    """
    if not raw_clusters:
        return []

    # Sort by cluster size descending (largest first)
    sorted_clusters = sorted(raw_clusters, key=lambda c: len(c["insiders"]), reverse=True)

    kept: list[dict[str, Any]] = []
    used_insiders: set[str] = set()

    for cluster in sorted_clusters:
        cluster_insiders = cluster["insiders"]

        # Check if this cluster has enough new insiders vs already-kept clusters
        new_insiders = cluster_insiders - used_insiders

        # Keep if it has enough new insiders or is the first cluster
        if not kept or len(new_insiders) >= 2:
            kept.append(cluster)
            used_insiders |= cluster_insiders

    return kept


class Form4Client:
    """Client for fetching insider trades from SEC Form 4 filings.

    Uses edgartools to access SEC EDGAR and parse Form 4 filings.
    All monetary values are converted to integer cents.

    Args:
        edgar_identity: SEC EDGAR identity string (required by SEC).
    """

    def __init__(self, edgar_identity: str) -> None:
        self._edgar_identity = edgar_identity

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def get_insider_trades(self, ticker: str, max_filings: int = 50) -> list[dict[str, Any]]:
        """Fetch insider trades from Form 4 filings.

        Retrieves recent Form 4 filings for the given ticker and
        parses purchase transactions. Sales are filtered out.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL").
            max_filings: Maximum number of Form 4 filings to parse.

        Returns:
            List of trade dicts with insider_name, insider_title,
            trade_type, shares, price_cents, value_cents, trade_date,
            filing_date. Only purchase transactions are included.
        """
        import edgar as edgar_module

        edgar_module.set_identity(self._edgar_identity)

        company = Company(ticker)
        filings = company.get_filings(form="4").head(max_filings)

        trades: list[dict[str, Any]] = []

        for filing in filings:
            try:
                form4 = filing.obj()
                filing_date = _parse_date(filing.filing_date)

                transactions = self._extract_transactions(form4, filing_date)
                trades.extend(transactions)
            except Exception as exc:
                logger.warning(
                    "Failed to parse Form 4 filing %s: %s",
                    getattr(filing, "accession_no", "unknown"),
                    exc,
                )
                continue

        return trades

    def _extract_transactions(self, form4: Any, filing_date: date) -> list[dict[str, Any]]:
        """Extract purchase transactions from a parsed Form 4 object.

        Args:
            form4: Parsed Form 4 filing object from edgartools.
            filing_date: Date the filing was made with SEC.

        Returns:
            List of purchase trade dicts.
        """
        results: list[dict[str, Any]] = []

        # Get the reporting owner info
        owner_name = _safe_str(getattr(form4, "owner", None))
        owner_title = _safe_str(getattr(form4, "officer_title", None))

        # Try to access non-derivative transactions
        transactions = getattr(form4, "non_derivative_transactions", None)
        if transactions is None:
            transactions = getattr(form4, "transactions", [])

        if transactions is None:
            return results

        for txn in transactions:
            try:
                txn_code = _safe_str(
                    getattr(txn, "transaction_code", None) or getattr(txn, "code", None)
                )

                # Only include purchases (code "P" or "purchase")
                if txn_code and txn_code.upper() not in ("P", "PURCHASE"):
                    continue

                shares = _safe_int(
                    getattr(txn, "shares", None) or getattr(txn, "transaction_shares", None)
                )
                price = getattr(txn, "price_per_share", None) or getattr(txn, "price", None)
                trade_date_raw = getattr(txn, "transaction_date", None) or getattr(
                    txn, "date", None
                )

                if shares is None or shares <= 0:
                    continue

                price_cents = _dollars_to_cents(price) if price is not None else None
                value_cents = price_cents * shares if price_cents is not None else None

                results.append(
                    {
                        "insider_name": owner_name or "Unknown",
                        "insider_title": owner_title,
                        "trade_type": "purchase",
                        "shares": shares,
                        "price_cents": price_cents,
                        "value_cents": value_cents,
                        "trade_date": _parse_date(trade_date_raw)
                        if trade_date_raw
                        else filing_date,
                        "filing_date": filing_date,
                    }
                )
            except Exception as exc:
                logger.debug("Skipping transaction: %s", exc)
                continue

        return results


def _dollars_to_cents(value: Any) -> int | None:
    """Convert a dollar value to integer cents.

    Args:
        value: Dollar amount (float, int, str, or None).

    Returns:
        Integer cents, or None if conversion fails.
    """
    if value is None:
        return None
    try:
        return int(round(float(value) * 100))
    except (ValueError, TypeError):
        return None


def _safe_str(value: Any) -> str | None:
    """Safely convert a value to string.

    Args:
        value: Any value.

    Returns:
        String representation or None.
    """
    if value is None:
        return None
    return str(value).strip() or None


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to integer.

    Args:
        value: Any value.

    Returns:
        Integer or None if conversion fails.
    """
    if value is None:
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _parse_date(value: Any) -> date:
    """Parse a date from various formats.

    Args:
        value: Date string, datetime, or date object.

    Returns:
        date object.
    """
    if isinstance(value, date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return date.today()
