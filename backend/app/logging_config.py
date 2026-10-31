"""Structured logging shared by the API and the worker.

Every record carries the current request id and task id (from context variables), so one task's
logs can be followed across the API, the worker, and asyncio.to_thread workers. LOG_FORMAT=json
emits one JSON object per line for log platforms; "text" is easier to read locally.
"""

import datetime
import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from typing import Optional

from .settings import settings

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
task_id_var: ContextVar[Optional[int]] = ContextVar("task_id", default=None)

_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Attributes every LogRecord has; anything else came from `extra=` and is emitted as a field
_STANDARD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}
_configured = False


def new_request_id(incoming: Optional[str] = None) -> str:
    """Reuses a caller-supplied X-Request-ID when well-formed (no log injection), else generates one."""
    if incoming and _VALID_REQUEST_ID.match(incoming):
        return incoming
    return uuid.uuid4().hex[:16]


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # An explicit `extra={"request_id": ...}` wins (e.g. error handlers running after the request scope)
        if getattr(record, "request_id", None) is None:
            record.request_id = request_id_var.get()
        if getattr(record, "task_id", None) is None:
            record.task_id = task_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "task_id"):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and key not in entry and key not in ("request_id", "task_id"):
                entry[key] = value
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        context = " ".join(
            f"{key}={getattr(record, key)}" for key in ("request_id", "task_id") if getattr(record, key, None) is not None
        )
        extras = " ".join(
            f"{key}={value}" for key, value in vars(record).items()
            if key not in _STANDARD_ATTRS and key not in ("request_id", "task_id")
        )
        line = f"{self.formatTime(record)} {record.levelname:<7} {record.name}: {record.getMessage()}"
        line += "".join(f" [{part}]" for part in (context, extras) if part)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(force: bool = False):
    """Installs the root handler once (API and worker both call this)."""
    global _configured
    if _configured and not force:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter() if settings.LOG_FORMAT.lower() == "json" else TextFormatter())
    root = logging.getLogger()
    for existing in [h for h in root.handlers if getattr(h, "_nimbus", False)]:
        root.removeHandler(existing)
    handler._nimbus = True
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())
    _configured = True
