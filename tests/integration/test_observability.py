"""Integration tests for Langfuse observability and budget invocation config.

Tests verify:
- Langfuse config creation with and without credentials
- Budget tracker bundling with invocation config
- Graceful degradation when Langfuse not configured
- Safe shutdown behavior
"""

from __future__ import annotations

import pytest

from ai_hedge_fund.agents.base import PipelineBudgetTracker
from ai_hedge_fund.observability.budget import create_invocation_config
from ai_hedge_fund.observability.langfuse import (
    create_langfuse_config,
    shutdown_langfuse,
)

# ---------------------------------------------------------------------------
# create_langfuse_config tests
# ---------------------------------------------------------------------------


def test_langfuse_config_has_thread_id():
    """create_langfuse_config returns dict with configurable thread_id."""
    config = create_langfuse_config("test-thread-001")
    assert "configurable" in config
    assert config["configurable"]["thread_id"] == "test-thread-001"


def test_langfuse_config_without_credentials_has_no_callbacks(monkeypatch: pytest.MonkeyPatch):
    """Without Langfuse credentials, config has no callbacks key."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    config = create_langfuse_config("test-thread-002")
    assert "callbacks" not in config


def test_langfuse_config_with_credentials_has_callbacks(monkeypatch: pytest.MonkeyPatch):
    """With Langfuse credentials set, config includes callbacks list."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test-123")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test-456")
    config = create_langfuse_config("test-thread-003")
    assert "callbacks" in config
    assert len(config["callbacks"]) == 1


def test_langfuse_config_with_credentials_has_metadata(monkeypatch: pytest.MonkeyPatch):
    """With Langfuse credentials set, config includes metadata."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test-123")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test-456")
    config = create_langfuse_config(
        "test-thread-004",
        session_id="session-001",
        tags=["test-tag"],
        user_id="test-user",
    )
    assert config["metadata"]["langfuse_session_id"] == "session-001"
    assert config["metadata"]["langfuse_user_id"] == "test-user"
    assert "test-tag" in config["metadata"]["langfuse_tags"]


# ---------------------------------------------------------------------------
# create_invocation_config tests
# ---------------------------------------------------------------------------


def test_invocation_config_returns_tuple(monkeypatch: pytest.MonkeyPatch):
    """create_invocation_config returns a (dict, PipelineBudgetTracker) tuple."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    config, tracker = create_invocation_config("run-001", "AAPL")
    assert isinstance(config, dict)
    assert isinstance(tracker, PipelineBudgetTracker)


def test_invocation_config_tracker_has_default_limit(monkeypatch: pytest.MonkeyPatch):
    """Budget tracker has total_limit from settings default (500,000)."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("PIPELINE_TOTAL_TOKEN_LIMIT", raising=False)
    _config, tracker = create_invocation_config("run-002", "MSFT")
    assert tracker.total_limit == 500_000


def test_invocation_config_includes_ticker_tag(monkeypatch: pytest.MonkeyPatch):
    """Config metadata includes ticker tag when Langfuse credentials set."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test-123")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test-456")
    config, _tracker = create_invocation_config("run-003", "TSLA")
    assert "ticker:TSLA" in config["metadata"]["langfuse_tags"]


def test_invocation_config_custom_tags(monkeypatch: pytest.MonkeyPatch):
    """Custom tags are merged with ticker tag in config metadata."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test-123")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test-456")
    config, _tracker = create_invocation_config(
        "run-004", "GOOG", tags=["sector:tech", "priority:high"]
    )
    tags = config["metadata"]["langfuse_tags"]
    assert "ticker:GOOG" in tags
    assert "sector:tech" in tags
    assert "priority:high" in tags


# ---------------------------------------------------------------------------
# shutdown_langfuse tests
# ---------------------------------------------------------------------------


def test_shutdown_langfuse_does_not_raise(monkeypatch: pytest.MonkeyPatch):
    """shutdown_langfuse does not raise even when Langfuse not configured."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    # Should not raise -- graceful degradation
    shutdown_langfuse()
