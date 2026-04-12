"""Structured logging configuration for Kalshi Backtesting Engine.

Switches between ConsoleRenderer (DEBUG) and JSONRenderer (INFO+).
Every module should use: logger = structlog.get_logger(__name__)
"""

from __future__ import annotations

import logging

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog with JSON (production) or console (development) output.

    Args:
        log_level: Logging level string (e.g., "DEBUG", "INFO", "WARNING").
            DEBUG -> ConsoleRenderer for human-readable output.
            INFO+ -> JSONRenderer for structured production logs.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if level == logging.DEBUG:
        processors = [*shared_processors, structlog.dev.ConsoleRenderer()]
    else:
        processors = [*shared_processors, structlog.processors.JSONRenderer()]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=level, format="%(message)s")
