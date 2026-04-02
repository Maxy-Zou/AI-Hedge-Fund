"""SEC filing retrieval client wrapping edgartools.

Fetches 10-K, 10-Q, and 8-K filings from SEC EDGAR, extracts section text
(business, risk factors, MD&A), validates section lengths, computes content
hashes, and returns typed FilingData objects.

Usage::

    with FilingClient(edgar_identity="YourCo you@example.com") as client:
        filings = client.get_latest_filings("10-K", cik="320193", count=5)
        for f in filings:
            print(f.accession_no, f.sections.business[:100])
"""

from __future__ import annotations

import hashlib
from datetime import date

import edgar
import structlog

from ai_washer.config import FilingCollectionSettings
from ai_washer.ingestion.types import FilingData, FilingSections

logger = structlog.get_logger(__name__)

# Minimum section length to consider valid (Pitfall 1 mitigation).
# Sections shorter than this are likely table-of-contents stubs, not
# real section content.
_MIN_SECTION_CHARS = 500

# Default form-type to settings-field mapping for count defaults.
_FORM_TYPE_COUNT_DEFAULTS = {
    "10-K": "max_annual_filings",
    "10-Q": "max_quarterly_filings",
    "8-K": "max_8k_filings",
}


class FilingClient:
    """Wrapper around edgartools for SEC filing retrieval and section extraction.

    Parameters
    ----------
    edgar_identity:
        SEC-compliant User-Agent string, e.g. "CompanyName email@example.com".
    settings:
        FilingCollectionSettings for section limits and filing counts.
    """

    def __init__(
        self,
        edgar_identity: str,
        settings: FilingCollectionSettings | None = None,
    ) -> None:
        self._edgar_identity = edgar_identity
        self._settings = settings or FilingCollectionSettings()
        self._log = logger.bind(client="filing_client")

        # Pitfall 5: Set edgartools identity before any API call
        edgar.set_identity(edgar_identity)

    # -- Context manager --------------------------------------------------

    def __enter__(self) -> FilingClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        # edgartools manages its own connections; nothing to close.
        pass

    # -- Public API -------------------------------------------------------

    def get_latest_filings(
        self,
        form_type: str,
        cik: str,
        count: int | None = None,
    ) -> list[FilingData]:
        """Retrieve the most recent filings of a given type for a company.

        Parameters
        ----------
        form_type:
            SEC form type -- "10-K", "10-Q", or "8-K".
        cik:
            Company CIK number (any format).
        count:
            Maximum number of filings to retrieve. Defaults to the
            appropriate setting (max_annual_filings for 10-K, etc.).

        Returns
        -------
        list[FilingData]
            Parsed filings with metadata and section text. Returns empty
            list on any error (CIK not found, API failure, etc.).
        """
        effective_count = count or self._default_count(form_type)
        log = self._log.bind(form_type=form_type, cik=cik, count=effective_count)

        try:
            company = edgar.Company(cik)
        except Exception:
            log.warning("filing_company_not_found", exc_info=True)
            return []

        try:
            filings_collection = company.get_filings(form=form_type)
            latest = filings_collection.latest(effective_count)
        except Exception:
            log.warning("filing_fetch_failed", exc_info=True)
            return []

        if latest is None:
            log.info("filing_none_found")
            return []

        # latest(1) returns a single object; latest(n>1) returns an iterable
        filing_items = self._to_iterable(latest)

        results: list[FilingData] = []
        for filing in filing_items:
            try:
                filing_data = self._extract_filing_data(filing, form_type)
                results.append(filing_data)
            except Exception:
                accession = getattr(filing, "accession_no", "unknown")
                log.warning(
                    "filing_extraction_failed",
                    accession_no=accession,
                    exc_info=True,
                )

        log.info("filing_fetch_complete", fetched=len(results))
        return results

    # -- Private ----------------------------------------------------------

    def _default_count(self, form_type: str) -> int:
        """Return the default filing count for a form type from settings."""
        attr_name = _FORM_TYPE_COUNT_DEFAULTS.get(form_type, "max_annual_filings")
        return getattr(self._settings, attr_name)

    def _to_iterable(self, latest: object) -> list:
        """Normalize edgartools latest() return to a list.

        latest(1) returns a single CompanyFiling object (has accession_no).
        latest(n>1) returns an EntityFilings collection (iterable).
        """
        # Single filing object: has accession_no attribute and is not a collection
        if hasattr(latest, "accession_no") and hasattr(latest, "obj"):
            return [latest]
        # Collection: iterate to list
        try:
            return list(latest)
        except TypeError:
            return [latest]

    def _extract_filing_data(self, filing: object, form_type: str) -> FilingData:
        """Parse a single edgartools filing into a FilingData object."""
        accession_no = getattr(filing, "accession_no", "")
        filing_date_str = getattr(filing, "filing_date", "")
        report_date_str = getattr(filing, "report_date", "")
        entity_name = getattr(filing, "company", None)

        filing_date_val = self._parse_date(filing_date_str)
        period_of_report_val = self._parse_date(report_date_str)

        sections = self._extract_sections(filing, form_type, accession_no)
        content_hash = self._compute_content_hash(sections)

        return FilingData(
            accession_no=accession_no,
            form_type=form_type,
            filing_date=filing_date_val,
            period_of_report=period_of_report_val,
            sections=sections,
            content_hash=content_hash,
            entity_name=entity_name,
        )

    def _extract_sections(
        self,
        filing: object,
        form_type: str,
        accession_no: str,
    ) -> FilingSections:
        """Extract section text based on form type."""
        if form_type == "10-K":
            return self._extract_10k_sections(filing, accession_no)
        if form_type == "10-Q":
            return self._extract_10q_sections(filing, accession_no)
        # 8-K and others: use full text excerpt
        return self._extract_8k_sections(filing, accession_no)

    def _extract_10k_sections(
        self,
        filing: object,
        accession_no: str,
    ) -> FilingSections:
        """Extract sections from a 10-K filing via edgartools TenK object."""
        max_chars = self._settings.section_max_chars
        has_short_section = False

        try:
            tenk = filing.obj()
        except Exception:
            self._log.warning(
                "filing_obj_failed",
                accession_no=accession_no,
                exc_info=True,
            )
            return self._fallback_sections(filing, accession_no)

        business = self._safe_section(tenk, "Item 1")
        risk_factors = self._safe_section(tenk, "Item 1A")
        mda = self._safe_section(tenk, "Item 7")

        # Validate section lengths (Pitfall 1 mitigation)
        for section_name, section_text in [
            ("business", business),
            ("risk_factors", risk_factors),
            ("mda", mda),
        ]:
            if not self._validate_section_length(
                section_text, section_name, accession_no
            ):
                has_short_section = True

        # Truncate to max chars (Pitfall 6 mitigation)
        business = self._truncate_section(business, max_chars)
        risk_factors = self._truncate_section(risk_factors, max_chars)
        mda = self._truncate_section(mda, max_chars)

        # Fallback: if any section is suspiciously short, populate full_text_excerpt
        full_text_excerpt = None
        if has_short_section:
            full_text_excerpt = self._get_full_text(filing, accession_no, max_chars)

        return FilingSections(
            business=business,
            risk_factors=risk_factors,
            mda=mda,
            full_text_excerpt=full_text_excerpt,
        )

    def _extract_10q_sections(
        self,
        filing: object,
        accession_no: str,
    ) -> FilingSections:
        """Extract sections from a 10-Q filing via edgartools TenQ object."""
        max_chars = self._settings.section_max_chars

        try:
            tenq = filing.obj()
        except Exception:
            self._log.warning(
                "filing_obj_failed",
                accession_no=accession_no,
                exc_info=True,
            )
            return self._fallback_sections(filing, accession_no)

        mda = self._safe_section(tenq, "part1item2")

        has_short = not self._validate_section_length(mda, "mda", accession_no)
        mda = self._truncate_section(mda, max_chars)

        full_text_excerpt = None
        if has_short:
            full_text_excerpt = self._get_full_text(filing, accession_no, max_chars)

        return FilingSections(
            mda=mda,
            full_text_excerpt=full_text_excerpt,
        )

    def _extract_8k_sections(
        self,
        filing: object,
        accession_no: str,
    ) -> FilingSections:
        """Extract content from an 8-K filing using full text."""
        max_chars = self._settings.section_max_chars
        full_text = self._get_full_text(filing, accession_no, max_chars)
        return FilingSections(full_text_excerpt=full_text)

    def _safe_section(self, filing_obj: object, key: str) -> str | None:
        """Safely extract a section from a filing object via bracket notation."""
        try:
            text = filing_obj[key]
            if text is None:
                return None
            return str(text)
        except (KeyError, IndexError, TypeError, Exception):
            return None

    def _get_full_text(
        self,
        filing: object,
        accession_no: str,
        max_chars: int,
    ) -> str | None:
        """Get full filing text as fallback, truncated to max_chars."""
        try:
            text = filing.text()
            return self._truncate_section(text, max_chars)
        except Exception:
            self._log.warning(
                "filing_text_failed",
                accession_no=accession_no,
                exc_info=True,
            )
            return None

    def _truncate_section(self, text: str | None, max_chars: int) -> str | None:
        """Truncate section text to max_chars if it exceeds the limit.

        Returns None if text is None.
        """
        if text is None:
            return None
        if len(text) > max_chars:
            return text[:max_chars]
        return text

    def _validate_section_length(
        self,
        text: str | None,
        section_name: str,
        filing_accession: str,
    ) -> bool:
        """Check if section text is suspiciously short.

        Returns True if valid (>= 500 chars or None), False if short.
        Logs a warning for short sections (Pitfall 1 mitigation).
        """
        if text is None:
            return True
        if len(text) < _MIN_SECTION_CHARS:
            self._log.warning(
                "filing_section_suspiciously_short",
                section=section_name,
                accession_no=filing_accession,
                char_count=len(text),
                threshold=_MIN_SECTION_CHARS,
            )
            return False
        return True

    def _compute_content_hash(self, sections: FilingSections) -> str:
        """Compute SHA-256 hash of all non-None section text concatenated."""
        concatenated = ""
        for field_val in [
            sections.business,
            sections.risk_factors,
            sections.mda,
            sections.financial_statements,
            sections.full_text_excerpt,
        ]:
            if field_val is not None:
                concatenated += field_val

        return hashlib.sha256(concatenated.encode()).hexdigest()

    def _parse_date(self, date_str: str | None) -> date:
        """Parse a date string (YYYY-MM-DD) into a date object.

        Returns date.min if parsing fails, to avoid crashing on bad data.
        """
        if not date_str:
            return date.min
        try:
            return date.fromisoformat(str(date_str))
        except (ValueError, TypeError):
            self._log.warning("filing_date_parse_failed", raw=date_str)
            return date.min

    def _fallback_sections(
        self,
        filing: object,
        accession_no: str,
    ) -> FilingSections:
        """Create FilingSections from full text when section parsing fails."""
        max_chars = self._settings.section_max_chars
        full_text = self._get_full_text(filing, accession_no, max_chars)
        return FilingSections(full_text_excerpt=full_text)
