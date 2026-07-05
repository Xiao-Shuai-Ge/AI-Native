"""Idempotency key helpers."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from orchestration.models import ToolCallRecord


def step_idempotency_key(task_id: UUID, step_name: str, operation: str | None = None) -> str:
    base = f"{task_id}:{step_name}"
    if operation:
        return f"{base}:{operation}"
    return base


def audit_idempotency_key(task_id: UUID, step: str, status: str) -> str:
    return f"{task_id}:{step}:{status}"


def tool_call_idempotency_key(
    task_id: UUID,
    step_name: str,
    call: ToolCallRecord,
    *,
    engine_suffix: str,
) -> str:
    """Stable key for one tool invocation within a task step."""
    effective_step = call.step_name or step_name
    started = call.started_at.isoformat() if call.started_at is not None else "unknown"
    args_blob = json.dumps(call.arguments, sort_keys=True, default=str)
    args_hash = hashlib.sha256(args_blob.encode()).hexdigest()[:16]
    return f"{task_id}:{effective_step}:{engine_suffix}:{call.tool_name}:{started}:{args_hash}"
