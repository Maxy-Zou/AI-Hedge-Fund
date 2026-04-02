"""Tests for KalshiClient — DATA-01 (RSA auth), DATA-03 (market filtering), DATA-05 (rate limit).

All tests are skipped until Plan 03 implements KalshiClient.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="KalshiClient not yet implemented — Plan 03")


def test_client_init_with_rsa_key() -> None:
    """DATA-01: KalshiClient initializes without error given valid RSA key path."""
    pytest.fail("Not yet implemented")


def test_rsa_headers_present() -> None:
    """DATA-01: RSA auth adds KALSHI-ACCESS-KEY header to every outbound request."""
    pytest.fail("Not yet implemented")


def test_markets_filtered_to_politics_series() -> None:
    """DATA-03: get_politics_markets() returns only markets matching allowed series tickers."""
    pytest.fail("Not yet implemented")


def test_rate_limit_enforced() -> None:
    """DATA-05: Client raises RateLimitError when calls exceed rate_limit_rpm."""
    pytest.fail("Not yet implemented")
