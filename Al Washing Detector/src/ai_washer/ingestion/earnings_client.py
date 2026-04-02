"""Earnings call transcript client wrapping the earningscall library.

Provides lazy API key validation, tenacity-based retry logic, and
structured TranscriptRecord output. Follows the same patterns as
GitHubClient (lazy token validation) and PatentSearchClient (lazy key).

Usage::

    client = EarningsClient(api_key="your-key")
    record = client.get_transcript("AAPL", 2024, 1)
    if record:
        print(record.text[:100], record.speakers)
"""

from __future__ import annotations

import earningscall
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ai_washer.ingestion.earnings_types import TranscriptRecord

logger = structlog.get_logger(__name__)


class EarningsClientError(Exception):
    """Raised when the earnings call client encounters an error."""


class EarningsClient:
    """Client for the earningscall library with lazy API key validation.

    Accepts an empty API key at construction time (lazy validation).
    Raises EarningsClientError on first API call if key is missing.
    Consistent with GitHubClient and PatentSearchClient patterns.

    Parameters
    ----------
    api_key:
        EarningsCall API key. Empty string accepted at construction;
        raises EarningsClientError on first call.
    """

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key
        self._log = logger.bind(client="earningscall")

    def _ensure_api_key(self) -> None:
        """Validate that an API key is set; raise if empty.

        Raises
        ------
        EarningsClientError
            If API key is empty.
        """
        if not self._api_key:
            raise EarningsClientError(
                "API key required. Set AI_WASHER_EARNINGSCALL_API_KEY "
                "environment variable or pass api_key to EarningsClient."
            )

    @retry(
        wait=wait_exponential(min=0.1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(ConnectionError),
        reraise=True,
    )
    def get_transcript(self, ticker: str, year: int, quarter: int) -> TranscriptRecord | None:
        """Retrieve an earnings call transcript for a ticker/year/quarter.

        Parameters
        ----------
        ticker:
            Stock ticker symbol, e.g. ``AAPL``.
        year:
            Fiscal year.
        quarter:
            Fiscal quarter (1-4).

        Returns
        -------
        TranscriptRecord | None
            Parsed transcript record, or None if no transcript exists.

        Raises
        ------
        EarningsClientError
            If API key is missing or the earningscall library raises.
        """
        self._ensure_api_key()

        try:
            earningscall.api_key = self._api_key
            company = earningscall.get_company(ticker)
            transcript = company.get_transcript(year=year, quarter=quarter)

            if transcript is None:
                self._log.info(
                    "transcript_not_found",
                    ticker=ticker,
                    year=year,
                    quarter=quarter,
                )
                return None

            # Extract speaker mapping from transcript
            speakers: dict[str, str] | None = None
            if transcript.speakers:
                speakers = {}
                for speaker in transcript.speakers:
                    if (
                        speaker.speaker_info
                        and speaker.speaker_info.title
                        and speaker.speaker_info.name
                    ):
                        speakers[speaker.speaker_info.title] = speaker.speaker_info.name

            # Extract transcript date from event
            transcript_date = None
            if transcript.event and transcript.event.conference_date:
                transcript_date = transcript.event.conference_date

            record = TranscriptRecord(
                ticker=ticker,
                year=year,
                quarter=quarter,
                transcript_date=transcript_date,
                text=transcript.text or "",
                speakers=speakers if speakers else None,
                source="earningscall",
            )

            self._log.info(
                "transcript_fetched",
                ticker=ticker,
                year=year,
                quarter=quarter,
                text_length=len(record.text),
            )

            return record

        except EarningsClientError:
            raise
        except Exception as exc:
            raise EarningsClientError(
                f"Failed to fetch transcript for {ticker} Q{quarter} {year}: {exc}"
            ) from exc

    def get_quarters_available(self, ticker: str) -> list[tuple[int, int]]:
        """Return available (year, quarter) pairs for a company.

        Parameters
        ----------
        ticker:
            Stock ticker symbol.

        Returns
        -------
        list[tuple[int, int]]
            List of (year, quarter) tuples.

        Raises
        ------
        EarningsClientError
            If API key is missing or earningscall library raises.
        """
        self._ensure_api_key()

        try:
            earningscall.api_key = self._api_key
            company = earningscall.get_company(ticker)
            events = company.events()

            result: list[tuple[int, int]] = []
            for event in events:
                if hasattr(event, "year") and hasattr(event, "quarter"):
                    result.append((event.year, event.quarter))

            self._log.info(
                "quarters_available",
                ticker=ticker,
                count=len(result),
            )
            return result

        except EarningsClientError:
            raise
        except Exception as exc:
            raise EarningsClientError(
                f"Failed to get available quarters for {ticker}: {exc}"
            ) from exc
