"""Tests for ingestion pipeline — DATA-01, DATA-02, DATA-04."""
import pytest


@pytest.mark.skip(reason="stub — implement in plan 03 after client.py exists")
def test_live_candlestick_fetch(load_fixture):
    """DATA-01: KalshiLiveClient returns CandlestickRecord list from fixture response."""
    pass


@pytest.mark.skip(reason="stub — implement in plan 03 after cutoff.py exists")
def test_cutoff_routing_historical(load_fixture):
    """DATA-02: Markets settled before cutoff are routed to historical client."""
    pass


@pytest.mark.skip(reason="stub — implement in plan 03 after cutoff.py exists")
def test_cutoff_routing_live(load_fixture):
    """DATA-02: Markets settled after cutoff are routed to live client."""
    pass


@pytest.mark.skip(reason="stub — implement in plan 04 after pipeline.py exists")
def test_idempotent_ingest(duckdb_con, load_fixture):
    """DATA-04: Running ingest twice on same fixture data inserts no duplicate candle rows."""
    pass
