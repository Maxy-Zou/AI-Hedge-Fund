"""Phase 10 T2 -- Alpaca paper settings on AppSettings (spec 1.1)."""

from __future__ import annotations

import pytest

from ai_hedge_fund.config import AppSettings


def test_alpaca_fields_exist_with_paper_host_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("ALPACA_PAPER_API_KEY", "ALPACA_PAPER_SECRET", "ALPACA_PAPER_HOST"):
        monkeypatch.delenv(var, raising=False)
    s = AppSettings(_env_file=None)
    assert s.alpaca_paper_api_key == ""
    assert s.alpaca_paper_secret == ""
    assert s.alpaca_paper_host == "https://paper-api.alpaca.markets"


def test_alpaca_fields_read_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "PKTEST")
    monkeypatch.setenv("ALPACA_PAPER_SECRET", "shh")
    s = AppSettings(_env_file=None)
    assert s.alpaca_paper_api_key == "PKTEST"
    assert s.alpaca_paper_secret == "shh"
