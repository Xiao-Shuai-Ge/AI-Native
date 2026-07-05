"""Task creation and query service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from events.schemas import AgentTaskEvent, AgentTaskEventPublisher
from orchestration.models import TaskRequest, TaskStatus
from observability.context import bind_task_context
from observability.tracing import inject_trace_headers, start_span
from persistence.dapr_state import DaprStateStore
from persistence.ids import new_task_id, thread_id_for, workflow_id_for
from persistence.repository import TaskRepository
from persistence.session_store import SessionStore
from persistence.state_machine import assert_transition
from workflows.client import WorkflowScheduler
from workflows.models import TaskWorkflowInput

logger = logging.getLogger(__name__)


class WorkflowScheduleError(RuntimeError):
    """Raised after task persistence is compensated for a workflow scheduling failure."""

    def __init__(self, task_id: UUID, message: str) -> None:
        super().__init__(message)
        self.task_id = task_id


class TaskService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        dapr_state: DaprStateStore,
        session_store: SessionStore,
        event_publisher: AgentTaskEventPublisher,
        workflow_scheduler: WorkflowScheduler,
        *,
        default_delay_seconds: float = 0.0,
    ) -> None:
        self._session_factory = session_factory
        self._dapr_state = dapr_state
        self._session_store = session_store
        self._event_publisher = event_publisher
        self._workflow_scheduler = workflow_scheduler
        self._default_delay_seconds = default_delay_seconds

    async def create_task(self, request: TaskRequest) -> dict[str, object]:
        task_id = new_task_id(request.task_id)
        session_id = request.session_id or uuid4()
        user_id = request.user_id or "default"
        workflow_id = workflow_id_for(task_id)
        thread_id = thread_id_for(task_id)
        delay_seconds = (
            request.delay_seconds
            if request.delay_seconds is not None
            else self._default_delay_seconds
        )

        with bind_task_context(
            task_id=str(task_id),
            engine=request.engine.value,
            workflow_id=workflow_id,
        ), start_span(
            "task.create",
            attributes={
                "task_id": str(task_id),
                "engine": request.engine.value,
                "workflow_id": workflow_id,
            },
        ):
            return await self._create_task_impl(
                request=request,
                task_id=task_id,
                session_id=session_id,
                user_id=user_id,
                workflow_id=workflow_id,
                thread_id=thread_id,
                delay_seconds=delay_seconds,
            )

    async def _create_task_impl(
        self,
        *,
        request: TaskRequest,
        task_id: UUID,
        session_id: UUID,
        user_id: str,
        workflow_id: str,
        thread_id: str,
        delay_seconds: float,
    ) -> dict[str, object]:
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
            "delay_seconds": delay_seconds,
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

        trace_headers = inject_trace_headers()
        wf_input = TaskWorkflowInput(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            user_query=request.user_query,
            engine_requested=request.engine.value,
            workflow_id=workflow_id,
            thread_id=thread_id,
            delay_seconds=delay_seconds,
            user_preferences=preferences,
            session_context=session_context,
            traceparent=trace_headers.get("traceparent"),
        )
        try:
            await self._workflow_scheduler.schedule_task(wf_input)
        except Exception as exc:
            await self._mark_scheduling_failed(
                task_id,
                engine=request.engine.value,
                error=str(exc),
            )
            msg = f"failed to schedule workflow for task {task_id}"
            raise WorkflowScheduleError(task_id, msg) from exc

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

    async def _mark_scheduling_failed(self, task_id: UUID, *, engine: str, error: str) -> None:
        error_summary = error[:500]
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_task(task_id)
            if task is not None:
                current = TaskStatus(task.status)
                if current == TaskStatus.QUEUED:
                    await repo.update_task_status(task_id, TaskStatus.RUNNING)
                    current = TaskStatus.RUNNING
                if current == TaskStatus.RUNNING:
                    await repo.update_task_status(task_id, TaskStatus.FAILED)
            await session.commit()

        try:
            await self._dapr_state.merge_task_runtime_state(
                task_id,
                {
                    "status": TaskStatus.FAILED.value,
                    "current_step": "scheduling_failed",
                    "error": error_summary,
                    "updated_at": datetime.now(tz=UTC).isoformat(),
                },
            )
        except Exception as exc:
            logger.warning(
                "failed to update dapr runtime state after workflow schedule failure",
                extra={"task_id": str(task_id), "error": str(exc)},
            )

        try:
            await self._event_publisher.publish(
                AgentTaskEvent(
                    task_id=task_id,
                    engine=engine,
                    step="workflow.schedule",
                    status=TaskStatus.FAILED.value,
                    detail=error_summary,
                )
            )
        except Exception as exc:
            logger.warning(
                "failed to publish workflow schedule failure event",
                extra={"task_id": str(task_id), "error": str(exc)},
            )

    async def pause_task(self, task_id: UUID) -> dict[str, object]:
        workflow_id = await self._load_workflow_id_for_transition(task_id, TaskStatus.PAUSED)

        await self._workflow_scheduler.pause_task(workflow_id)

        try:
            await self._persist_task_status(task_id, TaskStatus.PAUSED)
        except Exception as exc:
            try:
                await self._workflow_scheduler.resume_task(workflow_id)
            except Exception as compensate_exc:
                logger.error(
                    "failed to compensate workflow after pause persistence failure",
                    extra={
                        "task_id": str(task_id),
                        "workflow_id": workflow_id,
                        "error": str(compensate_exc),
                    },
                )
            msg = f"failed to persist paused status for task {task_id}"
            raise RuntimeError(msg) from exc

        try:
            await self._dapr_state.merge_task_runtime_state(
                task_id,
                {"status": TaskStatus.PAUSED.value},
            )
        except Exception as exc:
            logger.warning(
                "failed to update dapr runtime state on pause",
                extra={"task_id": str(task_id), "error": str(exc)},
            )

        return {
            "task_id": task_id,
            "workflow_id": workflow_id,
            "status": TaskStatus.PAUSED,
        }

    async def resume_task(self, task_id: UUID) -> dict[str, object]:
        workflow_id = await self._load_workflow_id_for_transition(task_id, TaskStatus.RUNNING)

        await self._workflow_scheduler.resume_task(workflow_id)

        try:
            await self._persist_task_status(task_id, TaskStatus.RUNNING)
        except Exception as exc:
            try:
                await self._workflow_scheduler.pause_task(workflow_id)
            except Exception as compensate_exc:
                logger.error(
                    "failed to compensate workflow after resume persistence failure",
                    extra={
                        "task_id": str(task_id),
                        "workflow_id": workflow_id,
                        "error": str(compensate_exc),
                    },
                )
            msg = f"failed to persist running status for task {task_id}"
            raise RuntimeError(msg) from exc

        try:
            await self._dapr_state.merge_task_runtime_state(
                task_id,
                {"status": TaskStatus.RUNNING.value},
            )
        except Exception as exc:
            logger.warning(
                "failed to update dapr runtime state on resume",
                extra={"task_id": str(task_id), "error": str(exc)},
            )

        return {
            "task_id": task_id,
            "workflow_id": workflow_id,
            "status": TaskStatus.RUNNING,
        }

    async def _load_workflow_id_for_transition(
        self,
        task_id: UUID,
        target: TaskStatus,
    ) -> str:
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_task(task_id)
            if task is None:
                msg = "task not found"
                raise LookupError(msg)
            current = TaskStatus(task.status)
            assert_transition(current, target)
            return task.workflow_id

    async def _persist_task_status(self, task_id: UUID, target: TaskStatus) -> None:
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_task(task_id)
            if task is None:
                msg = "task not found"
                raise LookupError(msg)
            current = TaskStatus(task.status)
            assert_transition(current, target)
            await repo.update_task_status(task_id, target)
            await session.commit()

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
