"""Dapr Pub/Sub helpers for agent task events."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from persistence.dapr_client import DaprHttpClient


class AgentTaskEvent(BaseModel):
    task_id: UUID
    engine: str
    step: str
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    detail: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


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
        data = event.model_dump(mode="json")
        await self._dapr.publish_event(self._topic, data)
