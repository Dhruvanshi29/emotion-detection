"""Structured JSON logging (Phase 15 P1 §5.1).

Emits one JSON object per log record with fields:
    ts, level, logger, msg, request_id, module, funcName, exc

Enabled when ``LOG_FORMAT=json`` (default in production). Falls back to the
plain formatter otherwise so local dev stays readable.
"""
from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any, Optional


# Populated by RequestIDMiddleware once per request; read by the formatter.
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Minimal, dependency-free JSON formatter."""

    _RESERVED = frozenset(
        {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "asctime",
            "taskName",
        }
    )

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
        }
        rid = request_id_ctx.get()
        if rid:
            payload["request_id"] = rid
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Any extras attached with logger.info("...", extra={...})
        for k, v in record.__dict__.items():
            if k in self._RESERVED or k.startswith("_"):
                continue
            if k in payload:
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        return json.dumps(payload, ensure_ascii=False)


def configure_json_logging(level: str = "INFO") -> None:
    """Replace root + uvicorn handlers with a single JSON stdout handler."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    lvl = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(lvl)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "app"):
        lg = logging.getLogger(name)
        lg.handlers[:] = [handler]
        lg.setLevel(lvl)
        lg.propagate = False
