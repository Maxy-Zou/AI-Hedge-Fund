"""CLI log routing: machine-readable stdout (--json) must not carry log lines."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import structlog

from ai_hedge_fund.logging import configure_logging, route_logs_to_stderr


@pytest.fixture(autouse=True)
def _restore_structlog() -> Iterator[None]:
    saved = structlog.get_config()
    yield
    structlog.configure(**saved)


def test_logs_go_to_stderr_not_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    route_logs_to_stderr()
    structlog.get_logger("t").info("hello_event", n=1)
    out, err = capsys.readouterr()
    assert out == ""
    assert "hello_event" in err


def test_follows_a_replaced_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    """Resolved per call, so a later sys.stderr swap (pytest capture) is honoured."""
    route_logs_to_stderr()
    capsys.readouterr()
    structlog.get_logger("t").info("second_event")
    assert "second_event" in capsys.readouterr().err


def test_overrides_a_prior_stdlib_configuration(capsys: pytest.CaptureFixture[str]) -> None:
    """configure_logging() installs stdlib-only processors; routing must not inherit them."""
    configure_logging("INFO")
    route_logs_to_stderr()
    structlog.get_logger("t").info("third_event")
    assert '"third_event"' in capsys.readouterr().err
