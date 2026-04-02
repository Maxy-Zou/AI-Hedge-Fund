"""Structured logging configuration using structlog."""

import structlog


def configure_logging(log_level: str = "INFO") -> structlog.stdlib.BoundLogger:
    """Configure structlog with JSON (production) or console (development) output.

    Args:
        log_level: Logging level string (e.g., "DEBUG", "INFO", "WARNING").

    Returns:
        A configured structlog BoundLogger instance.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer()
            if log_level == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger()
