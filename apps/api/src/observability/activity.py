"""Helpers for Dapr Workflow activity observability."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from observability.context import bind_task_context
from observability.tracing import attach_trace_context, start_span

logger = logging.getLogger(__name__)


def log_behavior(event: str, **fields: object) -> None:
    logger.info("agent.behavior", extra={"behavior_event": event, **fields})


async def run_with_activity_observability[T](
    *,
    activity_name: str,
    task_id: UUID | None,
    engine: str | None,
    traceparent: str | None,
    operation: Callable[[], Awaitable[T]],
) -> T:
    task_id_str = str(task_id) if task_id is not None else None
    with (
        attach_trace_context(traceparent),
        bind_task_context(
            task_id=task_id_str,
            engine=engine,
        ),
        start_span(
            f"workflow.activity.{activity_name}",
            attributes={
                "task_id": task_id_str,
                "engine": engine,
                "step": activity_name,
            },
        ),
    ):
        return await operation()
