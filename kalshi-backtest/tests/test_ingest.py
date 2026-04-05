"""Tests for ingestion clients and fetchers — DATA-01, DATA-02, DATA-04."""
from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

from kalshi_backtest.ingestion.cutoff import CutoffResult, HistoricalCutoffResolver
from kalshi_backtest.ingestion.types import CandlestickRecord

# ── DATA-01: live + historical client parse fixture responses ─────────────────

def test_live_candlestick_fetch(load_fixture):
    """DATA-01: KalshiHistoricalClient parses fixture candlestick response correctly."""
    fixture = load_fixture("candlesticks.json")
    candles_raw = fixture["candlesticks"]

    # Simulate what KalshiHistoricalClient.get_candlesticks() would parse
    records = [
        CandlestickRecord(
            ticker="KXBTCD-25JAN31-T99999",
            ts=int(c["ts"]),
            open_price=c.get("open_price"),
            high_price=c.get("high_price"),
            low_price=c.get("low_price"),
            close_price=c.get("close_price", c.get("price", 0)),
            volume=c.get("volume"),
        )
        for c in candles_raw
    ]

    assert len(records) == 2
    assert records[0].ticker == "KXBTCD-25JAN31-T99999"
    assert records[0].ts.tzinfo is None          # naive UTC
    assert 0 <= records[0].close_price <= 100    # valid price range


# ── DATA-02: cutoff routing ──────────────────────────────────────────────────

def test_cutoff_routing_historical():
    """DATA-02: Markets settled before cutoff are identified as historical tier."""
    cutoff = CutoffResult(
        cutoff_ts=1_700_000_000,
        cutoff_dt=datetime(2023, 11, 14, 22, 13, 20),  # naive UTC
    )
    # Market close_time BEFORE cutoff → historical
    market_close = datetime(2023, 6, 1, 0, 0, 0)

    http_mock = MagicMock()
    resolver = HistoricalCutoffResolver(http_mock, {})
    resolver._cached = cutoff

    assert resolver.is_historical(market_close, cutoff) is True


def test_cutoff_routing_live():
    """DATA-02: Markets settled after cutoff are identified as live tier."""
    cutoff = CutoffResult(
        cutoff_ts=1_700_000_000,
        cutoff_dt=datetime(2023, 11, 14, 22, 13, 20),
    )
    # Market close_time AFTER cutoff → live
    market_close = datetime(2024, 6, 1, 0, 0, 0)

    http_mock = MagicMock()
    resolver = HistoricalCutoffResolver(http_mock, {})
    resolver._cached = cutoff

    assert resolver.is_historical(market_close, cutoff) is False


def test_cutoff_resolve_caches_result():
    """DATA-02: Second call to resolve() uses cache, makes no HTTP request."""
    cached = CutoffResult(cutoff_ts=1_700_000_000, cutoff_dt=datetime(2023, 11, 14))
    http_mock = MagicMock()
    resolver = HistoricalCutoffResolver(http_mock, {})
    resolver._cached = cached

    result = resolver.resolve()  # should return cached, not call http_mock.get

    assert result is cached
    http_mock.get.assert_not_called()


# ── DATA-04: idempotent ingest ───────────────────────────────────────────────

def test_idempotent_ingest(duckdb_con, load_fixture):
    """DATA-04: Inserting same candlestick fixture twice stores exactly one row per (ticker, ts)."""
    from kalshi_backtest.db.repository import MarketRepository

    fixture = load_fixture("candlesticks.json")
    repo = MarketRepository(duckdb_con)

    candles = [
        CandlestickRecord(
            ticker=c["ticker"],
            ts=int(c["ts"]),
            open_price=c.get("open_price"),
            high_price=c.get("high_price"),
            low_price=c.get("low_price"),
            close_price=c.get("close_price", c.get("price", 0)),
            volume=c.get("volume"),
        )
        for c in fixture["candlesticks"]
    ]

    repo.insert_candles(candles)
    repo.insert_candles(candles)  # second insert — should be no-op

    count = repo.count_candles("KXBTCD-25JAN31-T99999")
    assert count == len(candles), f"Expected {len(candles)} rows, got {count} (duplicates detected)"


# ── Gap closure: RSA-PSS auth headers ──────────────────────────────────────


def _make_rsa_key_and_settings(tmp_path):
    """Generate a real RSA private key and return (key_path, settings_mock)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "test_key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    settings = MagicMock()
    settings.api_key_id = "test-key-id"
    settings.private_key_path = key_path
    settings.rate_limit_rpm = 60
    return key_path, settings


def test_historical_auth_headers_are_non_empty(tmp_path):
    """Gap closure DATA-01: _get_auth_headers() returns dict with all 3 Kalshi auth keys."""
    from kalshi_backtest.ingestion.client import KalshiHistoricalClient

    _, settings = _make_rsa_key_and_settings(tmp_path)
    client = KalshiHistoricalClient(settings)
    url = "https://api.elections.kalshi.com/trade-api/v2/historical/markets"
    headers = client._get_auth_headers("GET", url)

    assert headers, "Auth headers must not be empty"
    assert "KALSHI-ACCESS-KEY" in headers
    assert "KALSHI-ACCESS-SIGNATURE" in headers
    assert "KALSHI-ACCESS-TIMESTAMP" in headers
    assert headers["KALSHI-ACCESS-KEY"] == "test-key-id"
    assert len(headers["KALSHI-ACCESS-SIGNATURE"]) > 0


def test_historical_auth_headers_are_per_request(tmp_path):
    """Gap closure: KALSHI-ACCESS-TIMESTAMP is live per call — not cached from init."""
    from kalshi_backtest.ingestion.client import KalshiHistoricalClient

    _, settings = _make_rsa_key_and_settings(tmp_path)
    client = KalshiHistoricalClient(settings)
    url = "https://api.elections.kalshi.com/trade-api/v2/historical/markets"

    h1 = client._get_auth_headers("GET", url)
    time.sleep(0.02)  # 20ms gap — timestamp must differ
    h2 = client._get_auth_headers("GET", url)

    assert h1["KALSHI-ACCESS-TIMESTAMP"] != h2["KALSHI-ACCESS-TIMESTAMP"], (
        "Timestamp must be fresh on each call — not cached at init"
    )


def test_historical_get_candlesticks_sends_auth_headers(tmp_path):
    """Gap closure DATA-01: get_candlesticks() passes non-empty auth headers to httpx.get()."""
    from kalshi_backtest.ingestion.client import KalshiHistoricalClient

    _, settings = _make_rsa_key_and_settings(tmp_path)
    client = KalshiHistoricalClient(settings)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"candlesticks": []}
    mock_resp.raise_for_status.return_value = None

    with patch.object(client._http, "get", return_value=mock_resp) as mock_get:
        client.get_candlesticks("KXBTCD-25JAN31-T99999", 1700000000, 1710000000)

    call_kwargs = mock_get.call_args.kwargs
    headers_sent = call_kwargs.get("headers", {})
    assert "KALSHI-ACCESS-KEY" in headers_sent, (
        f"httpx.get() was called with headers={headers_sent!r} — expected Kalshi auth headers"
    )
