"""MinimalTaskRunner unit and integration tests."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.config import get_settings
from api.services.minimal_runner import MinimalTaskRunner
from events.schemas import AgentTaskEventPublisher
from orchestration.models import EngineChoice, TaskStatus
from persistence.dapr_state import DaprStateStore
from persistence.database import build_async_database_url
from persistence.repository import TaskRepository


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    settings = get_settings()
    engine = create_async_engine(build_async_database_url(settings), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _runner(session_factory: async_sessionmaker[AsyncSession]) -> MinimalTaskRunner:
    dapr_client = AsyncMock()
    dapr_state = DaprStateStore(dapr_client)
    dapr_state.merge_task_runtime_state = AsyncMock()  # type: ignore[method-assign]
    publisher = AgentTaskEventPublisher(dapr_client)
    publisher.publish = AsyncMock()  # type: ignore[method-assign]
    return MinimalTaskRunner(session_factory, dapr_state, publisher)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_task_failed_from_queued(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task_id = uuid4()
    async with session_factory() as session:
        repo = TaskRepository(session)
        await repo.create_task(
            task_id=task_id,
            session_id=uuid4(),
            user_id="default",
            user_query="fail early",
            engine_requested=EngineChoice.AUTO,
            workflow_id=f"wf-{task_id}",
            thread_id=str(task_id),
        )
        await session.commit()

    runner = _runner(session_factory)
    await runner._mark_task_failed(task_id)

    async with session_factory() as session:
        repo = TaskRepository(session)
        task = await repo.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED.value


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_task_failed_from_paused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task_id = uuid4()
    async with session_factory() as session:
        repo = TaskRepository(session)
        await repo.create_task(
            task_id=task_id,
            session_id=uuid4(),
            user_id="default",
            user_query="paused task",
            engine_requested=EngineChoice.LANGGRAPH,
            workflow_id=f"wf-{task_id}",
            thread_id=str(task_id),
        )
        await repo.update_task_status(task_id, TaskStatus.RUNNING)
        await repo.update_task_status(task_id, TaskStatus.PAUSED)
        await session.commit()

    runner = _runner(session_factory)
    await runner._mark_task_failed(task_id)

    async with session_factory() as session:
        repo = TaskRepository(session)
        task = await repo.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.FAILED.value


@pytest.mark.asyncio
async def test_update_runtime_state_merges_without_dropping_context(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task_id = uuid4()
    runner = _runner(session_factory)
    dapr_state = runner._dapr_state
    assert isinstance(dapr_state.merge_task_runtime_state, AsyncMock)

    await runner._update_runtime_state(task_id, TaskStatus.RUNNING, current_step="plan")

    dapr_state.merge_task_runtime_state.assert_awaited_once()
    patch = dapr_state.merge_task_runtime_state.await_args.args[1]
    assert patch["status"] == TaskStatus.RUNNING.value
    assert patch["current_step"] == "plan"
    assert patch["task_id"] == str(task_id)
