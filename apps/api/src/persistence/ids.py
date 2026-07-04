"""Stable ID generation for tasks."""

from uuid import UUID, uuid4


def new_task_id(requested: UUID | None = None) -> UUID:
    return requested or uuid4()


def workflow_id_for(task_id: UUID) -> str:
    return f"wf-{task_id}"


def thread_id_for(task_id: UUID) -> str:
    return str(task_id)
