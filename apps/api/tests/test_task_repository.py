"""Task repository integration tests."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.config import get_settings
from orchestration.models import EngineChoice, TaskStatus
from persistence.database import build_async_database_url
from persistence.idempotency import audit_idempotency_key, step_idempotency_key
from persistence.repository import TaskRepository


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    settings = get_settings()
    engine = create_async_engine(build_async_database_url(settings), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_record_step_is_idempotent(session_factory: async_sessionmaker[AsyncSession]) -> None:
    task_id = uuid4()
    async with session_factory() as session:
        repo = TaskRepository(session)
        await repo.create_task(
            task_id=task_id,
            session_id=uuid4(),
            user_id="default",
            user_query="test",
            engine_requested=EngineChoice.AUTO,
            workflow_id=f"wf-{task_id}",
            thread_id=str(task_id),
        )
        key = step_idempotency_key(task_id, "plan")
        first = await repo.record_step(
            task_id=task_id,
            step_name="plan",
            status="completed",
            output_json={"ok": True},
            idempotency_key=key,
        )
        second = await repo.record_step(
            task_id=task_id,
            step_name="plan",
            status="completed",
            output_json={"ok": True},
            idempotency_key=key,
        )
        await session.commit()
        assert first is not None
        assert second is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_record_audit_event_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task_id = uuid4()
    async with session_factory() as session:
        repo = TaskRepository(session)
        await repo.create_task(
            task_id=task_id,
            session_id=uuid4(),
            user_id="default",
            user_query="test",
            engine_requested=EngineChoice.AUTO,
            workflow_id=f"wf-{task_id}",
            thread_id=str(task_id),
        )
        key = audit_idempotency_key(task_id, "plan", "completed")
        first = await repo.record_audit_event(
            task_id=task_id,
            engine="langgraph",
            step="plan",
            status="completed",
            payload={"detail": "done"},
            event_time=datetime.now(tz=UTC),
            idempotency_key=key,
        )
        second = await repo.record_audit_event(
            task_id=task_id,
            engine="langgraph",
            step="plan",
            status="completed",
            payload={"detail": "done"},
            event_time=datetime.now(tz=UTC),
            idempotency_key=key,
        )
        await session.commit()
        assert first is not None
        assert second is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_status_transition_validation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task_id = uuid4()
    async with session_factory() as session:
        repo = TaskRepository(session)
        await repo.create_task(
            task_id=task_id,
            session_id=uuid4(),
            user_id="default",
            user_query="test",
            engine_requested=EngineChoice.AUTO,
            workflow_id=f"wf-{task_id}",
            thread_id=str(task_id),
        )
        await repo.update_task_status(task_id, TaskStatus.RUNNING)
        with pytest.raises(ValueError, match="invalid task status transition"):
            await repo.update_task_status(task_id, TaskStatus.QUEUED)
        await session.commit()
