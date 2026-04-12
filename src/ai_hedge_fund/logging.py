"""Structured logging configuration using structlog.

Produces JSON-formatted log output with UTC timestamps, log level,
and caller information. Designed for agent-level log binding where
each agent run can attach contextual fields (ticker, model_tier, etc.).
"""

from __future__ import annotations

import logging

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
