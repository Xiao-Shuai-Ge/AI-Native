"""Consume agent.task.events and persist audit records."""

import logging

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from events.broadcaster import TaskEventBroadcaster
from events.schemas import AgentTaskEvent
from persistence.idempotency import audit_idempotency_key
from persistence.repository import TaskRepository

logger = logging.getLogger(__name__)


class AgentTaskEventHandler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        broadcaster: TaskEventBroadcaster | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._broadcaster = broadcaster

    async def handle_payload(self, payload: dict[str, object]) -> bool:
        try:
            event = AgentTaskEvent.model_validate(payload)
        except ValidationError as exc:
            logger.warning("invalid agent task event", extra={"error": str(exc)})
            return False

        idempotency_key = audit_idempotency_key(event.task_id, event.step, event.status)
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            record = await repo.record_audit_event(
                task_id=event.task_id,
                engine=event.engine,
                step=event.step,
                status=event.status,
                payload={
                    "detail": event.detail,
                    **event.payload,
                },
                event_time=event.timestamp,
                idempotency_key=idempotency_key,
            )
            await session.commit()
            created = record is not None

        if created and self._broadcaster is not None:
            await self._broadcaster.publish(event)
        return created

    async def handle_dapr_envelope(self, envelope: dict[str, object]) -> bool:
        data = envelope.get("data")
        if isinstance(data, str):
            import json

            payload = json.loads(data)
        elif isinstance(data, dict):
            payload = data
        else:
            payload = envelope
        return await self.handle_payload(payload)
