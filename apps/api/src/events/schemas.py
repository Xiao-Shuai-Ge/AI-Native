"""Dapr Pub/Sub helpers for agent task events."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from observability.context import bind_task_context
from observability.tracing import current_trace_id, inject_trace_headers, start_span
from persistence.dapr_client import DaprHttpClient


class AgentTaskEvent(BaseModel):
    task_id: UUID
    engine: str
    step: str
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    detail: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    trace_id: str | None = None
    traceparent: str | None = None


class AgentTaskEventPublisher:
    def __init__(
        self,
        dapr: DaprHttpClient,
        *,
        topic: str = "agent.task.events",
    ) -> None:
        self._dapr = dapr
        self._topic = topic

    async def publish(self, event: AgentTaskEvent) -> None:
        trace_id = current_trace_id()
        traceparent = inject_trace_headers().get("traceparent")
        updates: dict[str, str] = {}
        if trace_id is not None and event.trace_id is None:
            updates["trace_id"] = trace_id
        if traceparent and event.traceparent is None:
            updates["traceparent"] = traceparent
        if updates:
            event = event.model_copy(update=updates)
        with bind_task_context(task_id=str(event.task_id), engine=event.engine), start_span(
            "pubsub.agent_task_event",
            attributes={
                "task_id": str(event.task_id),
                "engine": event.engine,
                "step": event.step,
                "status": event.status,
                "trace_id": event.trace_id,
            },
        ):
            data = event.model_dump(mode="json")
            await self._dapr.publish_event(self._topic, data)
