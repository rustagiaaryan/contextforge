"""Minimal JSON structured logging for service adapters."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Format standard log records as one-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str | None = None) -> None:
    """Configure the root logger once using the documented environment level."""
    root = logging.getLogger()
    if any(isinstance(handler.formatter, JsonFormatter) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    selected_level = level or os.getenv("CONTEXTFORGE_LOG_LEVEL") or "INFO"
    root.setLevel(selected_level.upper())
