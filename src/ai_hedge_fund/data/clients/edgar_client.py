"""SEC EDGAR filing client via edgartools.

Retrieves 10-K, 10-Q, and 8-K filings with section-level extraction.
Filters by filing_date (not period end date) to prevent look-ahead bias.
Uses tenacity retry for resilience against transient SEC API failures.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import edgar
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger(__name__)

# Section mappings by form type
_10K_SECTIONS: dict[str, str] = {
    "Item 1": "business",
    "Item 1A": "risk_factors",
    "Item 7": "mda",
}

_10Q_SECTIONS: dict[str, str] = {
    "part1item2": "mda",
}

_FULL_TEXT_MAX_CHARS = 50_000


class EdgarClient:
    """Wrapper around edgartools for SEC EDGAR filing retrieval.

    Sets the SEC EDGAR identity on construction (required by SEC for
    identification). All external calls use tenacity retry with exponential
    backoff.

    Args:
        edgar_identity: Identity string for SEC EDGAR (e.g., "Company email@example.com").
    """

    def __init__(self, edgar_identity: str) -> None:
        self._identity = edgar_identity
        edgar.set_identity(edgar_identity)
        log.info("edgar_client.init", identity=edgar_identity)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_filings(
        self,
        ticker: str,
        form_type: str,
        max_filings: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve filing metadata for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL").
            form_type: SEC form type (e.g., "10-K", "10-Q").
            max_filings: Maximum number of filings to return.

        Returns:
            List of filing metadata dicts sorted by filing_date descending.
            Each dict has keys: accession_no, filing_date, form_type, company_name.
        """
        log.info("edgar_client.get_filings", ticker=ticker, form_type=form_type)
        company = edgar.Company(ticker)
        raw_filings = company.get_filings(form=form_type).head(max_filings)

        results = []
        for f in raw_filings:
            filing_date = f.filing_date
            if isinstance(filing_date, str):
                filing_date = date.fromisoformat(filing_date)

            results.append(
                {
                    "accession_no": f.accession_no,
                    "filing_date": filing_date,
                    "form_type": f.form,
                    "company_name": getattr(f, "company", ""),
                }
            )

        # Sort by filing_date descending
        results.sort(key=lambda r: r["filing_date"], reverse=True)
        return results

    def get_filing_sections(
        self,
        ticker: str,
        form_type: str,
        filing_date_cutoff: date,
        max_filings: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve filings with extracted sections, filtered by date.

        Filters out filings where filing_date > filing_date_cutoff to prevent
        look-ahead bias. Extracts named sections based on form type.
        Falls back to truncated full text if all sections return None.

        Args:
            ticker: Stock ticker symbol.
            form_type: SEC form type ("10-K" or "10-Q").
            filing_date_cutoff: Maximum filing_date to include (inclusive).
            max_filings: Maximum number of filings to retrieve.

        Returns:
            List of dicts with keys: accession_no, filing_date, form_type,
            sections (dict of section_name -> text).
        """
        log.info(
            "edgar_client.get_filing_sections",
            ticker=ticker,
            form_type=form_type,
            cutoff=filing_date_cutoff.isoformat(),
        )

        company = edgar.Company(ticker)
        raw_filings = company.get_filings(form=form_type).head(max_filings)

        section_map = _10K_SECTIONS if form_type == "10-K" else _10Q_SECTIONS

        results = []
        for f in raw_filings:
            filing_date = f.filing_date
            if isinstance(filing_date, str):
                filing_date = date.fromisoformat(filing_date)

            # Filter by filing_date cutoff (prevent look-ahead bias)
            if filing_date > filing_date_cutoff:
                log.debug(
                    "edgar_client.skipping_future_filing",
                    accession_no=f.accession_no,
                    filing_date=filing_date.isoformat(),
                )
                continue

            # Extract sections
            sections: dict[str, str | None] = {}
            for key, name in section_map.items():
                sections[name] = self._safe_section(f, key)

            # Fallback to full text if all sections are None
            has_content = any(v is not None for v in sections.values())
            if not has_content:
                try:
                    full = f.text()
                    sections = {"full_text": full[:_FULL_TEXT_MAX_CHARS] if full else None}
                except Exception:
                    log.warning(
                        "edgar_client.full_text_fallback_failed",
                        accession_no=f.accession_no,
                    )
                    sections = {"full_text": None}

            results.append(
                {
                    "accession_no": f.accession_no,
                    "filing_date": filing_date,
                    "form_type": f.form,
                    "sections": sections,
                }
            )

        # Sort by filing_date descending
        results.sort(key=lambda r: r["filing_date"], reverse=True)
        return results

    @staticmethod
    def _safe_section(filing: Any, key: str) -> str | None:
        """Safely extract a section from a filing object.

        Args:
            filing: An edgartools filing object supporting bracket notation.
            key: Section key (e.g., "Item 1", "Item 1A").

        Returns:
            Section text as string, or None if not available.
        """
        try:
            value = filing[key]
            if value is None:
                return None
            return str(value)
        except (KeyError, IndexError, TypeError, AttributeError):
            return None
