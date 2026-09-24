"""Phase 10 T5 -- recursive secret redaction (09-PREMORTEM #7).

Phase 9's payload tripwire only checks top-level keys; the broker
request/response nests credentials, so redaction must run at every depth
before anything becomes a stored ``payload``.
"""

from __future__ import annotations

from ai_hedge_fund.execution.redact import redact


def test_top_level_secret_key_redacted() -> None:
    out = redact({"api_key": "PKLIVE", "symbol": "AAPL"})
    assert out["api_key"] == "***"
    assert out["symbol"] == "AAPL"


def test_nested_secret_keys_redacted() -> None:
    out = redact({"config": {"secret": "s", "nested": {"authorization": "Bearer x"}}})
    assert out["config"]["secret"] == "***"
    assert out["config"]["nested"]["authorization"] == "***"


def test_secret_inside_list_redacted() -> None:
    out = redact({"headers": [{"token": "abc"}, {"symbol": "AAPL"}]})
    assert out["headers"][0]["token"] == "***"
    assert out["headers"][1]["symbol"] == "AAPL"


def test_configured_secret_values_scrubbed_from_strings() -> None:
    """A known key/secret appearing as a value (even under a benign key) is scrubbed."""
    out = redact({"url": "https://x?key=SUPERSECRET"}, secret_values=["SUPERSECRET"])
    assert "SUPERSECRET" not in out["url"]


def test_non_secret_data_unchanged() -> None:
    data = {"symbol": "AAPL", "qty": 10, "nested": {"side": "buy"}}
    assert redact(data) == data


def test_original_not_mutated() -> None:
    data = {"api_key": "PK"}
    redact(data)
    assert data["api_key"] == "PK"  # redact returns a copy
