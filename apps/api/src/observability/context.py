"""Task-scoped context propagated through logs and spans."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)
_engine_var: ContextVar[str | None] = ContextVar("engine", default=None)
_workflow_id_var: ContextVar[str | None] = ContextVar("workflow_id", default=None)


def get_task_id() -> str | None:
    return _task_id_var.get()


def get_engine() -> str | None:
    return _engine_var.get()


def get_workflow_id() -> str | None:
    return _workflow_id_var.get()


def task_context_fields() -> dict[str, str]:
    fields: dict[str, str] = {}
    task_id = get_task_id()
    engine = get_engine()
    workflow_id = get_workflow_id()
    if task_id is not None:
        fields["task_id"] = task_id
    if engine is not None:
        fields["engine"] = engine
    if workflow_id is not None:
        fields["workflow_id"] = workflow_id
    return fields


@contextmanager
def bind_task_context(
    *,
    task_id: str | None = None,
    engine: str | None = None,
    workflow_id: str | None = None,
) -> Iterator[None]:
    tokens: list[tuple[ContextVar[str | None], object]] = []
    if task_id is not None:
        tokens.append((_task_id_var, _task_id_var.set(task_id)))
    if engine is not None:
        tokens.append((_engine_var, _engine_var.set(engine)))
    if workflow_id is not None:
        tokens.append((_workflow_id_var, _workflow_id_var.set(workflow_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
