"""Structured JSON logging (Art VI.4 — stdlib logging + JSON formatter).

Configured once at app startup via :func:`configure_logging`. Library code
calls :func:`get_logger` and uses standard `logging` semantics; the formatter
turns every record into a single-line JSON document with all `extra={...}`
fields merged into the top level.
"""

from __future__ import annotations

import json
import logging
import logging.config
from datetime import UTC, datetime
from typing import Any, Final

_RESERVED_LOGRECORD_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonFormatter(logging.Formatter):
    """Render each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    """Install :class:`JsonFormatter` as the root handler.

    Idempotent: re-calling replaces the existing handler set rather than
    stacking duplicates (matters for the FastAPI lifespan, which can be
    invoked multiple times in test runs).
    """
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "rag.log.JsonFormatter",
                },
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": level.upper(),
                "handlers": ["stdout"],
            },
            "loggers": {
                "uvicorn": {"level": level.upper(), "handlers": ["stdout"], "propagate": False},
                "uvicorn.error": {
                    "level": level.upper(),
                    "handlers": ["stdout"],
                    "propagate": False,
                },
                "uvicorn.access": {
                    "level": level.upper(),
                    "handlers": ["stdout"],
                    "propagate": False,
                },
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    """Return a logger that respects the global JSON config."""
    return logging.getLogger(name)
