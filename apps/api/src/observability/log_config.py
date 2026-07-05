"""JSON structured logging with trace/task context and redaction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from observability.context import task_context_fields
from observability.tracing import current_trace_id

_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}"), "[REDACTED]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"postgresql://[^\s\"']+", re.IGNORECASE), "postgresql://[REDACTED]"),
    (re.compile(r"redis://[^\s\"']+", re.IGNORECASE), "redis://[REDACTED]"),
    (re.compile(r"(api[_-]?key\s*[:=]\s*)[^\s,\"']+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(password\s*[:=]\s*)[^\s,\"']+", re.IGNORECASE), r"\1[REDACTED]"),
)

_SENSITIVE_EXTRA_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "deepseek_api_key",
        "openai_api_key",
        "anthropic_api_key",
        "postgres_password",
        "redis_password",
    }
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _REDACT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in _SENSITIVE_EXTRA_KEYS else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(str(record.msg))
        for key, value in list(record.__dict__.items()):
            if key in {
                "msg",
                "args",
                "name",
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
                "message",
            }:
                continue
            setattr(record, key, _redact_value(value))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }

        trace_id = current_trace_id()
        if trace_id is not None:
            payload["trace_id"] = trace_id
        payload.update(task_context_fields())

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "msg",
                "args",
                "name",
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
                "message",
            }:
                continue
            payload[key] = _redact_value(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(*, level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.setLevel(level)
