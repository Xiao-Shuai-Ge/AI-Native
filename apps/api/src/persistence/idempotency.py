"""Idempotency key helpers."""

from uuid import UUID


def step_idempotency_key(task_id: UUID, step_name: str, operation: str | None = None) -> str:
    base = f"{task_id}:{step_name}"
    if operation:
        return f"{base}:{operation}"
    return base


def audit_idempotency_key(task_id: UUID, step: str, status: str) -> str:
    return f"{task_id}:{step}:{status}"
