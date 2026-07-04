"""Task event broadcaster tests."""

import asyncio
from uuid import uuid4

import pytest

from events.broadcaster import TaskEventBroadcaster
from events.schemas import AgentTaskEvent


@pytest.mark.asyncio
async def test_broadcaster_delivers_event_to_subscriber() -> None:
    broadcaster = TaskEventBroadcaster()
    task_id = uuid4()
    queue = broadcaster.subscribe(task_id)

    event = AgentTaskEvent(
        task_id=task_id,
        engine="langgraph",
        step="researcher",
        status="running",
    )
    await broadcaster.publish(event)

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received == event

    broadcaster.unsubscribe(task_id, queue)
