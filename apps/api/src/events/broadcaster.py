"""In-process broadcaster for SSE task event streams."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

from events.schemas import AgentTaskEvent


@dataclass
class TaskEventBroadcaster:
    """Fan-out agent task events to SSE subscribers within the same API process."""

    _subscribers: dict[UUID, set[asyncio.Queue[AgentTaskEvent | None]]] = field(
        default_factory=lambda: defaultdict(set)
    )

    def subscribe(self, task_id: UUID) -> asyncio.Queue[AgentTaskEvent | None]:
        queue: asyncio.Queue[AgentTaskEvent | None] = asyncio.Queue()
        self._subscribers[task_id].add(queue)
        return queue

    def unsubscribe(self, task_id: UUID, queue: asyncio.Queue[AgentTaskEvent | None]) -> None:
        subscribers = self._subscribers.get(task_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(task_id, None)

    async def publish(self, event: AgentTaskEvent) -> None:
        for queue in list(self._subscribers.get(event.task_id, ())):
            await queue.put(event)

    async def close(self, task_id: UUID) -> None:
        for queue in list(self._subscribers.get(task_id, ())):
            await queue.put(None)

    async def stream(self, task_id: UUID) -> AsyncIterator[AgentTaskEvent]:
        queue = self.subscribe(task_id)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            self.unsubscribe(task_id, queue)
