"""Task creation and query service."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.services.minimal_runner import MinimalTaskRunner
from events.schemas import AgentTaskEventPublisher
from orchestration.models import TaskRequest, TaskStatus
from persistence.dapr_state import DaprStateStore
from persistence.ids import new_task_id, thread_id_for, workflow_id_for
from persistence.repository import TaskRepository
from persistence.session_store import SessionStore

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        dapr_state: DaprStateStore,
        session_store: SessionStore,
        event_publisher: AgentTaskEventPublisher,
    ) -> None:
        self._session_factory = session_factory
        self._dapr_state = dapr_state
        self._session_store = session_store
        self._runner = MinimalTaskRunner(session_factory, dapr_state, event_publisher)

    async def create_task(self, request: TaskRequest) -> dict[str, object]:
        task_id = new_task_id(request.task_id)
        session_id = request.session_id or uuid4()
        user_id = request.user_id or "default"
        workflow_id = workflow_id_for(task_id)
        thread_id = thread_id_for(task_id)

        async with self._session_factory() as session:
            repo = TaskRepository(session)
            if request.task_id is not None and await repo.task_exists(task_id):
                msg = f"task already exists: {task_id}"
                raise ValueError(msg)

            preferences = await repo.get_user_preferences(user_id)
            session_context = await self._session_store.get_messages(user_id, session_id)

            await repo.create_task(
                task_id=task_id,
                session_id=session_id,
                user_id=user_id,
                user_query=request.user_query,
                engine_requested=request.engine,
                workflow_id=workflow_id,
                thread_id=thread_id,
            )
            await repo.record_message(
                task_id=task_id,
                session_id=session_id,
                role="user",
                content=request.user_query,
            )
            await session.commit()

        runtime_snapshot: dict[str, object] = {
            "task_id": str(task_id),
            "session_id": str(session_id),
            "user_id": user_id,
            "status": TaskStatus.QUEUED.value,
            "engine_requested": request.engine.value,
            "user_query": request.user_query,
            "workflow_id": workflow_id,
            "thread_id": thread_id,
            "session_context": session_context,
            "user_preferences": preferences,
        }
        try:
            await self._dapr_state.save_task_runtime_state(task_id, runtime_snapshot)
        except Exception as exc:
            logger.warning(
                "failed to write initial dapr state",
                extra={"task_id": str(task_id), "error": str(exc)},
            )

        await self._session_store.append_message(
            user_id,
            session_id,
            role="user",
            content=request.user_query,
        )

        asyncio.create_task(self._runner.run(task_id))

        return {
            "task_id": task_id,
            "session_id": session_id,
            "workflow_id": workflow_id,
            "thread_id": thread_id,
            "status": TaskStatus.QUEUED,
            "engine_requested": request.engine,
            "user_preferences": preferences,
            "session_context": session_context,
        }

    async def get_task(self, task_id: UUID) -> dict[str, object] | None:
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_task(task_id)
            if task is None:
                return None
            payload = _serialize_task(task)

        runtime = None
        try:
            runtime = await self._dapr_state.get_task_runtime_state(task_id)
        except Exception as exc:
            logger.warning(
                "failed to read dapr runtime state",
                extra={"task_id": str(task_id), "error": str(exc)},
            )
        if runtime is not None:
            payload["runtime_state"] = runtime
        return payload

    async def list_tasks(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, object]]:
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            tasks = await repo.list_tasks(limit=limit, offset=offset)
            return [_serialize_task(task) for task in tasks]


def _serialize_task(task: object) -> dict[str, object]:
    from persistence.models import TaskRecord

    if not isinstance(task, TaskRecord):
        msg = "expected TaskRecord"
        raise TypeError(msg)

    return {
        "task_id": task.id,
        "session_id": task.session_id,
        "user_id": task.user_id,
        "user_query": task.user_query,
        "engine_requested": task.engine_requested,
        "engine_selected": task.engine_selected,
        "engine_selection_reason": task.engine_selection_reason,
        "status": task.status,
        "workflow_id": task.workflow_id,
        "thread_id": task.thread_id,
        "report": task.report,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "steps": [
            {
                "id": step.id,
                "step_name": step.step_name,
                "status": step.status,
                "output_json": step.output_json,
                "created_at": step.created_at,
            }
            for step in task.steps
        ],
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in task.messages
        ],
        "audit_events": [
            {
                "id": event.id,
                "engine": event.engine,
                "step": event.step,
                "status": event.status,
                "payload": event.payload,
                "event_time": event.event_time,
            }
            for event in task.audit_events
        ],
        "tool_calls": [
            {
                "id": call.id,
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "result_summary": call.result_summary,
                "error": call.error,
                "started_at": call.started_at,
                "finished_at": call.finished_at,
            }
            for call in task.tool_calls
        ],
    }
