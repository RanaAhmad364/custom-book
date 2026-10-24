from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from flask import Flask, has_request_context, request


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if has_request_context():
            entry.update(
                request_id=getattr(request, "request_id", None),
                method=request.method,
                path=request.path,
            )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(app: Flask) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(app.config["LOG_LEVEL"].upper())
    app.logger.propagate = False
