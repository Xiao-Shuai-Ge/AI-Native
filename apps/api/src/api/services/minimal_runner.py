"""Minimal async task runner for Day 3 persistence smoke path."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from events.schemas import AgentTaskEvent, AgentTaskEventPublisher
from orchestration.models import EngineChoice, TaskStatus
from persistence.dapr_state import DaprStateStore
from persistence.idempotency import step_idempotency_key
from persistence.repository import TaskRepository
from workflows.event_messages import (
    step_finished_detail,
    task_started_detail,
    task_succeeded_detail,
)

logger = logging.getLogger(__name__)

STUB_STEPS: tuple[tuple[str, str], ...] = (
    ("plan", "completed"),
    ("writer", "completed"),
)


class MinimalTaskRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        dapr_state: DaprStateStore,
        event_publisher: AgentTaskEventPublisher,
    ) -> None:
        self._session_factory = session_factory
        self._dapr_state = dapr_state
        self._event_publisher = event_publisher

    async def run(self, task_id: UUID) -> None:
        try:
            async with self._session_factory() as session:
                repo = TaskRepository(session)
                task = await repo.get_task(task_id)
                if task is None:
                    return
                engine = EngineChoice(task.engine_requested)
                await repo.update_task_status(task_id, TaskStatus.RUNNING, engine_selected=engine)
                await session.commit()

            await self._publish_and_persist(
                task_id,
                engine=engine.value,
                step="task",
                status=TaskStatus.RUNNING.value,
                detail=task_started_detail(),
            )
            await self._update_runtime_state(task_id, TaskStatus.RUNNING, current_step="plan")

            for step_name, step_status in STUB_STEPS:
                await self._publish_and_persist(
                    task_id,
                    engine=engine.value,
                    step=step_name,
                    status=step_status,
                    detail=step_finished_detail(step_name),
                )
                async with self._session_factory() as session:
                    repo = TaskRepository(session)
                    await repo.record_step(
                        task_id=task_id,
                        step_name=step_name,
                        status=step_status,
                        output_json={"detail": f"{step_name} 占位输出"},
                        idempotency_key=step_idempotency_key(task_id, step_name),
                    )
                    await session.commit()
                await self._update_runtime_state(
                    task_id, TaskStatus.RUNNING, current_step=step_name
                )

            report = f"Stub report for task {task_id}"
            async with self._session_factory() as session:
                repo = TaskRepository(session)
                await repo.update_task_status(
                    task_id,
                    TaskStatus.SUCCEEDED,
                    report=report,
                )
                await session.commit()

            await self._publish_and_persist(
                task_id,
                engine=engine.value,
                step="task",
                status=TaskStatus.SUCCEEDED.value,
                detail=task_succeeded_detail(),
            )
            await self._update_runtime_state(
                task_id,
                TaskStatus.SUCCEEDED,
                current_step="done",
                report=report,
            )
        except Exception as exc:
            logger.exception("minimal runner failed", extra={"task_id": str(task_id)})
            await self._mark_task_failed(task_id)
            await self._publish_and_persist(
                task_id,
                engine="unknown",
                step="task",
                status=TaskStatus.FAILED.value,
                detail=str(exc),
            )

    async def _publish_and_persist(
        self,
        task_id: UUID,
        *,
        engine: str,
        step: str,
        status: str,
        detail: str,
    ) -> None:
        event = AgentTaskEvent(
            task_id=task_id,
            engine=engine,
            step=step,
            status=status,
            timestamp=datetime.now(tz=UTC),
            detail=detail,
        )
        try:
            await self._event_publisher.publish(event)
        except Exception as exc:
            logger.warning(
                "failed to publish agent task event",
                extra={"task_id": str(task_id), "step": step, "error": str(exc)},
            )

    async def _update_runtime_state(
        self,
        task_id: UUID,
        status: TaskStatus,
        *,
        current_step: str,
        report: str | None = None,
    ) -> None:
        snapshot: dict[str, object] = {
            "task_id": str(task_id),
            "status": status.value,
            "current_step": current_step,
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }
        if report is not None:
            snapshot["report"] = report
        try:
            await self._dapr_state.merge_task_runtime_state(task_id, snapshot)
        except Exception as exc:
            logger.warning(
                "failed to save dapr runtime state",
                extra={"task_id": str(task_id), "error": str(exc)},
            )

    async def _mark_task_failed(self, task_id: UUID) -> None:
        async with self._session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_task(task_id)
            if task is None:
                return
            current = TaskStatus(task.status)
            if current in (TaskStatus.SUCCEEDED, TaskStatus.CANCELLED, TaskStatus.FAILED):
                return
            if current in (TaskStatus.QUEUED, TaskStatus.PAUSED):
                await repo.update_task_status(task_id, TaskStatus.RUNNING)
            await repo.update_task_status(task_id, TaskStatus.FAILED)
            await session.commit()
