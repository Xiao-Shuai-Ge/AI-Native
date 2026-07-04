"""PostgreSQL repositories for tasks and audit records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestration.models import EngineChoice, TaskStatus
from persistence.models import (
    AuditEventRecord,
    TaskMessageRecord,
    TaskRecord,
    TaskStepRecord,
    UserPreferenceRecord,
)
from persistence.state_machine import assert_transition


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_task(self, task_id: UUID) -> TaskRecord | None:
        result = await self._session.execute(select(TaskRecord).where(TaskRecord.id == task_id))
        return result.scalar_one_or_none()

    async def task_exists(self, task_id: UUID) -> bool:
        task = await self.get_task(task_id)
        return task is not None

    async def create_task(
        self,
        *,
        task_id: UUID,
        session_id: UUID | None,
        user_id: str,
        user_query: str,
        engine_requested: EngineChoice,
        workflow_id: str,
        thread_id: str,
    ) -> TaskRecord:
        record = TaskRecord(
            id=task_id,
            session_id=session_id,
            user_id=user_id,
            user_query=user_query,
            engine_requested=engine_requested.value,
            status=TaskStatus.QUEUED.value,
            workflow_id=workflow_id,
            thread_id=thread_id,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def update_task_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        *,
        engine_selected: EngineChoice | None = None,
        engine_selection_reason: str | None = None,
        report: str | None = None,
    ) -> TaskRecord | None:
        task = await self.get_task(task_id)
        if task is None:
            return None
        current = TaskStatus(task.status)
        assert_transition(current, status)
        task.status = status.value
        if engine_selected is not None:
            task.engine_selected = engine_selected.value
        if engine_selection_reason is not None:
            task.engine_selection_reason = engine_selection_reason
        if report is not None:
            task.report = report
        await self._session.flush()
        return task

    async def list_tasks(self, *, limit: int = 50, offset: int = 0) -> list[TaskRecord]:
        stmt: Select[tuple[TaskRecord]] = (
            select(TaskRecord).order_by(TaskRecord.created_at.desc()).limit(limit).offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def record_step(
        self,
        *,
        task_id: UUID,
        step_name: str,
        status: str,
        output_json: dict[str, object] | None,
        idempotency_key: str,
    ) -> TaskStepRecord | None:
        existing = await self._session.execute(
            select(TaskStepRecord).where(TaskStepRecord.idempotency_key == idempotency_key)
        )
        found = existing.scalar_one_or_none()
        if found is not None:
            return None

        record = TaskStepRecord(
            task_id=task_id,
            step_name=step_name,
            status=status,
            output_json=output_json,
            idempotency_key=idempotency_key,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def record_message(
        self,
        *,
        task_id: UUID,
        session_id: UUID | None,
        role: str,
        content: str,
    ) -> TaskMessageRecord:
        record = TaskMessageRecord(
            task_id=task_id,
            session_id=session_id,
            role=role,
            content=content,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def record_audit_event(
        self,
        *,
        task_id: UUID,
        engine: str,
        step: str,
        status: str,
        payload: dict[str, object],
        event_time: datetime,
        idempotency_key: str,
    ) -> AuditEventRecord | None:
        existing = await self._session.execute(
            select(AuditEventRecord).where(AuditEventRecord.idempotency_key == idempotency_key)
        )
        found = existing.scalar_one_or_none()
        if found is not None:
            return None

        record = AuditEventRecord(
            task_id=task_id,
            engine=engine,
            step=step,
            status=status,
            payload=payload,
            event_time=event_time,
            idempotency_key=idempotency_key,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_user_preferences(self, user_id: str) -> dict[str, object]:
        result = await self._session.execute(
            select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return {}
        return dict(record.preferences)

    async def upsert_user_preferences(
        self, user_id: str, preferences: dict[str, object]
    ) -> UserPreferenceRecord:
        result = await self._session.execute(
            select(UserPreferenceRecord).where(UserPreferenceRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = UserPreferenceRecord(user_id=user_id, preferences=preferences)
            self._session.add(record)
        else:
            record.preferences = preferences
        await self._session.flush()
        return record
