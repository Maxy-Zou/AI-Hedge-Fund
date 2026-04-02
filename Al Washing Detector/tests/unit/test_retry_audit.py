"""Retry decorator audit across all API clients (OPS-01).

Static introspection tests that verify all 7 API clients have tenacity
retry decorators with exponential backoff. No HTTP calls are made -- this
is a regression guard ensuring retry coverage is not accidentally removed.

The 7 clients are:
1. EdgarFactsClient (edgar_client.py)
2. EFTSClient (efts_client.py)
3. PatentSearchClient (patent_client.py)
4. GitHubClient (github_client.py)
5. EarningsClient (earnings_client.py)
6. JobClient (job_client.py)
7. XBRLExtractor (xbrl_extractor.py)

Note: FilingClient wraps edgartools (which handles its own retries)
and is not a direct HTTP client, so it is excluded from this audit.
"""

from __future__ import annotations

import pytest
from tenacity import wait_exponential
from tenacity.stop import stop_after_attempt

from ai_washer.ingestion.earnings_client import EarningsClient
from ai_washer.ingestion.edgar_client import EdgarFactsClient
from ai_washer.ingestion.efts_client import EFTSClient
from ai_washer.ingestion.github_client import GitHubClient
from ai_washer.ingestion.job_client import JobClient
from ai_washer.ingestion.patent_client import PatentSearchClient
from ai_washer.ingestion.xbrl_extractor import XBRLExtractor


# Each tuple: (class, method_name that should have @retry)
_RETRY_AUDIT_CASES = [
    (EdgarFactsClient, "_fetch_json", "EdgarFactsClient._fetch_json"),
    (EFTSClient, "_fetch_page", "EFTSClient._fetch_page"),
    (PatentSearchClient, "_fetch_page", "PatentSearchClient._fetch_page"),
    (GitHubClient, "_get", "GitHubClient._get"),
    (EarningsClient, "get_transcript", "EarningsClient.get_transcript"),
    (JobClient, "search_company_jobs", "JobClient.search_company_jobs"),
    (XBRLExtractor, "_fetch_json", "XBRLExtractor._fetch_json"),
]


def _get_retry_attr(cls: type, method_name: str):  # noqa: ANN202
    """Get the retry attribute from a method, handling bound/unbound methods."""
    method = getattr(cls, method_name, None)
    if method is None:
        return None
    # tenacity attaches a .retry attribute to decorated functions
    return getattr(method, "retry", None)


class TestRetryDecoratorPresence:
    """Verify all 7 API clients have tenacity @retry on their HTTP methods."""

    @pytest.mark.parametrize(
        ("cls", "method_name", "label"),
        _RETRY_AUDIT_CASES,
        ids=[c[2] for c in _RETRY_AUDIT_CASES],
    )
    def test_method_has_retry_decorator(
        self, cls: type, method_name: str, label: str
    ) -> None:
        """Each client's HTTP method must have a tenacity retry decorator."""
        retry_state = _get_retry_attr(cls, method_name)
        assert retry_state is not None, (
            f"{label} is missing @retry decorator. "
            f"All API client HTTP methods must have tenacity retry."
        )


class TestRetryConfiguration:
    """Verify retry configs use exponential backoff with bounded attempts."""

    @pytest.mark.parametrize(
        ("cls", "method_name", "label"),
        _RETRY_AUDIT_CASES,
        ids=[c[2] for c in _RETRY_AUDIT_CASES],
    )
    def test_uses_exponential_backoff(
        self, cls: type, method_name: str, label: str
    ) -> None:
        """Each retry config must use wait_exponential."""
        retry_state = _get_retry_attr(cls, method_name)
        assert retry_state is not None, f"{label} missing @retry"

        wait = retry_state.wait
        # wait may be a composed wait or directly wait_exponential
        is_exponential = isinstance(wait, wait_exponential)
        # Some may use wait_combine or similar; check string representation
        if not is_exponential:
            wait_str = str(type(wait).__name__)
            # Accept any wait that contains exponential as a component
            assert "exponential" in repr(wait).lower(), (
                f"{label} retry wait strategy does not include exponential backoff. "
                f"Got: {wait_str}"
            )

    @pytest.mark.parametrize(
        ("cls", "method_name", "label"),
        _RETRY_AUDIT_CASES,
        ids=[c[2] for c in _RETRY_AUDIT_CASES],
    )
    def test_has_stop_after_attempt(
        self, cls: type, method_name: str, label: str
    ) -> None:
        """Each retry config must have stop_after_attempt (max attempts)."""
        retry_state = _get_retry_attr(cls, method_name)
        assert retry_state is not None, f"{label} missing @retry"

        stop = retry_state.stop
        is_stop_attempt = isinstance(stop, stop_after_attempt)
        if not is_stop_attempt:
            # Accept composed stop strategies that include stop_after_attempt
            assert "attempt" in repr(stop).lower(), (
                f"{label} retry stop strategy does not include stop_after_attempt. "
                f"Got: {type(stop).__name__}"
            )

    @pytest.mark.parametrize(
        ("cls", "method_name", "label"),
        _RETRY_AUDIT_CASES,
        ids=[c[2] for c in _RETRY_AUDIT_CASES],
    )
    def test_max_attempts_is_reasonable(
        self, cls: type, method_name: str, label: str
    ) -> None:
        """Max attempts should be between 2 and 10 (inclusive)."""
        retry_state = _get_retry_attr(cls, method_name)
        assert retry_state is not None, f"{label} missing @retry"

        stop = retry_state.stop
        if isinstance(stop, stop_after_attempt):
            max_attempts = stop.max_attempt_number
            assert 2 <= max_attempts <= 10, (
                f"{label} has {max_attempts} max attempts -- "
                f"expected between 2 and 10."
            )
