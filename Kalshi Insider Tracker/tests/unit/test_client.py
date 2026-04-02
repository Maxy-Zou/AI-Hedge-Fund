"""Tests for KalshiClient — DATA-01 (RSA auth), DATA-03 (filtering), DATA-05 (rate limit)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kalshi_tracker.config import KalshiSettings


@pytest.fixture
def mock_settings(tmp_path: Path) -> KalshiSettings:
    """KalshiSettings with a real temp file as private_key_path (no actual key needed for init)."""
    key_file = tmp_path / "fake_key.pem"
    key_file.write_text("-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n")
    return KalshiSettings(
        api_key_id="test-key-id",
        private_key_path=str(key_file),
        api_base_url="https://demo-api.kalshi.co/trade-api/v2",
        rate_limit_rpm=60,
        politics_series=["PRES", "SENATE"],
    )


def test_client_init_with_rsa_key(mock_settings: KalshiSettings, tmp_path: Path) -> None:
    """DATA-01: KalshiClient initializes without error given a valid key file path."""
    with patch("kalshi_tracker.kalshi.client.ApiClient") as mock_api_client_cls:
        mock_instance = MagicMock()
        mock_api_client_cls.return_value = mock_instance

        from kalshi_tracker.kalshi.client import KalshiClient
        KalshiClient(mock_settings)

        # SDK ApiClient was constructed
        mock_api_client_cls.assert_called_once()


def test_rsa_headers_present(mock_settings: KalshiSettings) -> None:
    """DATA-01: set_kalshi_auth() is called with correct key_id and private_key_path."""
    with patch("kalshi_tracker.kalshi.client.ApiClient") as mock_api_client_cls:
        mock_instance = MagicMock()
        mock_api_client_cls.return_value = mock_instance

        from kalshi_tracker.kalshi.client import KalshiClient
        KalshiClient(mock_settings)

        mock_instance.set_kalshi_auth.assert_called_once_with(
            key_id="test-key-id",
            private_key_path=str(mock_settings.private_key_path),
        )


def test_markets_filtered_to_politics_series(mock_settings: KalshiSettings) -> None:
    """DATA-03: get_politics_markets() only fetches from politics_series allowlist."""
    with patch("kalshi_tracker.kalshi.client.ApiClient"), \
         patch("kalshi_tracker.kalshi.client.MarketsApi") as mock_markets_api_cls:

        mock_api = MagicMock()
        mock_markets_api_cls.return_value = mock_api

        # Mock response: each series returns one market
        mock_market = MagicMock()
        mock_market.ticker = "PRES-2024-DEM-J"
        mock_market.series_ticker = "PRES"
        mock_market.title = "Test market"
        mock_market.yes_bid = 45
        mock_market.yes_ask = 47
        mock_market.no_bid = 53
        mock_market.no_ask = 55
        mock_market.last_price = 46
        mock_market.volume = 1000
        mock_market.volume_24h = 200
        mock_market.status = "active"

        mock_response = MagicMock()
        mock_response.markets = [mock_market]
        mock_response.cursor = None
        mock_api.get_markets.return_value = mock_response

        from kalshi_tracker.kalshi.client import KalshiClient
        client = KalshiClient(mock_settings)
        client.get_politics_markets()

        # Called once per series in allowlist (PRES + SENATE = 2 calls)
        assert mock_api.get_markets.call_count == 2
        # Verify series_ticker was passed for each allowlist entry
        call_kwargs = [c.kwargs for c in mock_api.get_markets.call_args_list]
        series_used = [kw["series_ticker"] for kw in call_kwargs]
        assert sorted(series_used) == sorted(mock_settings.politics_series)


def test_get_politics_markets_returns_snapshots(mock_settings: KalshiSettings) -> None:
    """DATA-03: get_politics_markets() returns list[MarketSnapshot], not raw SDK objects."""
    from kalshi_tracker.kalshi.types import MarketSnapshot

    with patch("kalshi_tracker.kalshi.client.ApiClient"), \
         patch("kalshi_tracker.kalshi.client.MarketsApi") as mock_markets_api_cls:

        mock_api = MagicMock()
        mock_markets_api_cls.return_value = mock_api

        mock_market = MagicMock()
        mock_market.ticker = "PRES-2024-DEM-J"
        mock_market.series_ticker = "PRES"
        mock_market.title = "Democrat wins presidency"
        mock_market.yes_bid = 45
        mock_market.yes_ask = 47
        mock_market.no_bid = 53
        mock_market.no_ask = 55
        mock_market.last_price = 46
        mock_market.volume = 500
        mock_market.volume_24h = 100
        mock_market.status = "active"

        mock_response = MagicMock()
        mock_response.markets = [mock_market]
        mock_response.cursor = None
        mock_api.get_markets.return_value = mock_response

        from kalshi_tracker.kalshi.client import KalshiClient
        client = KalshiClient(mock_settings)
        snapshots = client.get_politics_markets()

        assert all(isinstance(s, MarketSnapshot) for s in snapshots)
        # Prices are int (normalized from SDK's Union[StrictFloat, StrictInt])
        first = next(s for s in snapshots if s.ticker == "PRES-2024-DEM-J")
        assert isinstance(first.yes_bid, int)
        assert first.yes_bid == 45


def test_rate_limit_enforced(mock_settings: KalshiSettings) -> None:
    """DATA-05: RateLimitError raised when calls exceed rate_limit_rpm."""
    from kalshi_tracker.kalshi.client import RateLimitError, _TokenBucket

    # Create a bucket with rate=2 per minute (very low for testing)
    bucket = _TokenBucket(rate_per_minute=2)
    bucket.consume()   # 1st: OK
    bucket.consume()   # 2nd: OK (bucket starts full)

    # Force tokens to 0 to test the limit
    bucket._tokens = 0.0
    with pytest.raises(RateLimitError):
        bucket.consume()   # Should raise — bucket empty
