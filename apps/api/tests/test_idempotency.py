"""Idempotency key tests."""

from uuid import UUID

from persistence.idempotency import audit_idempotency_key, step_idempotency_key

TASK_ID = UUID("11111111-1111-1111-1111-111111111111")


def test_step_idempotency_key_without_operation() -> None:
    assert step_idempotency_key(TASK_ID, "plan") == f"{TASK_ID}:plan"


def test_step_idempotency_key_with_operation() -> None:
    assert step_idempotency_key(TASK_ID, "plan", "persist") == f"{TASK_ID}:plan:persist"


def test_audit_idempotency_key_excludes_timestamp() -> None:
    key = audit_idempotency_key(TASK_ID, "plan", "completed")
    assert key == f"{TASK_ID}:plan:completed"
    assert "T" not in key
