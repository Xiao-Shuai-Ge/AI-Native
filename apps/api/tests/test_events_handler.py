"""Agent task event handler tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from events.handler import AgentTaskEventHandler
from persistence.models import AuditEventRecord


@pytest.mark.asyncio
async def test_handle_payload_persists_new_event(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = session

    handler = AgentTaskEventHandler(session_factory)
    task_id = uuid4()
    payload = {
        "task_id": str(task_id),
        "engine": "langgraph",
        "step": "plan",
        "status": "completed",
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }

    repo = AsyncMock()
    repo.record_audit_event = AsyncMock(
        return_value=AuditEventRecord(
            id=uuid4(),
            task_id=task_id,
            engine="langgraph",
            step="plan",
            status="completed",
            payload={},
            event_time=datetime.now(tz=UTC),
            idempotency_key=f"{task_id}:plan:completed",
        )
    )
    monkeypatch.setattr("events.handler.TaskRepository", lambda _session: repo)
    created = await handler.handle_payload(payload)

    assert created is True
    repo.record_audit_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_payload_deduplicates_event(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session_factory = MagicMock()
    session_factory.return_value.__aenter__.return_value = session

    handler = AgentTaskEventHandler(session_factory)
    task_id = uuid4()
    payload = {
        "task_id": str(task_id),
        "engine": "langgraph",
        "step": "plan",
        "status": "completed",
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }

    repo = AsyncMock()
    repo.record_audit_event = AsyncMock(return_value=None)
    monkeypatch.setattr("events.handler.TaskRepository", lambda _session: repo)
    created = await handler.handle_payload(payload)

    assert created is False
