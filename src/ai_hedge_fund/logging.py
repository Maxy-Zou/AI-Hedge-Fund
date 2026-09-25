"""Structured logging configuration using structlog.

Produces JSON-formatted log output with UTC timestamps, log level,
and caller information. Designed for agent-level log binding where
each agent run can attach contextual fields (ticker, model_tier, etc.).
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO") -> structlog.stdlib.BoundLogger:
    """Configure structlog with JSON output and UTC timestamps.

    Args:
        log_level: Python log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        A bound structlog logger ready for use.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog's formatter with JSON renderer
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer()
        if log_level == "DEBUG"
        else structlog.processors.JSONRenderer(),
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    return structlog.get_logger()


class _StderrLoggerFactory:
    """PrintLogger bound to whatever ``sys.stderr`` is *now* (not at configure time)."""

    def __call__(self, *_args: object) -> structlog.PrintLogger:
        return structlog.PrintLogger(sys.stderr)


def route_logs_to_stderr() -> None:
    """Send structlog output to stderr so a CLI's stdout stays machine-readable.

    Unconfigured structlog prints to stdout, which corrupted ``--json`` output
    (found in Phase 11). A complete, self-contained configuration: it must not
    inherit stdlib-only processors a prior :func:`configure_logging` installed.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=_StderrLoggerFactory(),
        cache_logger_on_first_use=False,
    )
