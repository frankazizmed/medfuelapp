from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Per-task context that downstream log records inherit. Bound at job entry so
# adapter/extract/render logs can be correlated to a single discovery run
# without threading the id through every function signature.
_JOB_CONTEXT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "medfuel_job_context", default=None
)


def bind_job_context(**fields: Any) -> None:
    current = dict(_JOB_CONTEXT.get() or {})
    current.update({k: v for k, v in fields.items() if v is not None})
    _JOB_CONTEXT.set(current)


def clear_job_context() -> None:
    _JOB_CONTEXT.set(None)


def get_job_context() -> dict[str, Any]:
    return dict(_JOB_CONTEXT.get() or {})


class JSONFormatter(logging.Formatter):
    """One JSON object per record so downstream collectors can parse without regex."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        ctx = get_job_context()
        if ctx:
            payload.update(ctx)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Any extra attached via logger.info(..., extra={...}) lands here.
        for key, value in record.__dict__.items():
            if key in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "message", "module",
                "msecs", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName", "taskName",
            }:
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter at the root logger. Safe to call multiple times."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    # Remove any pre-installed handlers so uvicorn/pytest don't double-print.
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
