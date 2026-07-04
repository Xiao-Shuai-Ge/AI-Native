"""Pause and resume task API tests."""

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from api.config import get_settings
from api.deps import build_app_state
from api.main import app
from orchestration.models import TaskStatus
from persistence.repository import TaskRepository


@pytest.fixture
async def client() -> AsyncClient:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def _set_task_status(task_id: str, status: TaskStatus) -> None:
    state = build_app_state(get_settings())
    try:
        async with state.session_factory() as session:
            repo = TaskRepository(session)
            task = await repo.get_task(UUID(task_id))
            if task is None:
                msg = f"task not found: {task_id}"
                raise LookupError(msg)
            current = TaskStatus(task.status)
            if current != status:
                from persistence.state_machine import assert_transition

                assert_transition(current, status)
                await repo.update_task_status(UUID(task_id), status)
            await session.commit()
    finally:
        state.workflow_scheduler.close()
        await state.engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pause_running_task(client: AsyncClient) -> None:
    with (
        patch("workflows.client.WorkflowScheduler.schedule_task", new=AsyncMock()),
        patch("workflows.client.WorkflowScheduler.pause_task", new=AsyncMock()) as pause_mock,
    ):
        create_response = await client.post(
            "/api/tasks",
            json={"user_query": "pause me", "engine": "auto"},
        )
        assert create_response.status_code == 201
        task_id = create_response.json()["task_id"]

        await _set_task_status(task_id, TaskStatus.RUNNING)

        pause_response = await client.post(f"/api/tasks/{task_id}/pause")
        assert pause_response.status_code == 200
        body = pause_response.json()
        assert body["status"] == "paused"
        pause_mock.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resume_paused_task(client: AsyncClient) -> None:
    with (
        patch("workflows.client.WorkflowScheduler.schedule_task", new=AsyncMock()),
        patch("workflows.client.WorkflowScheduler.resume_task", new=AsyncMock()) as resume_mock,
    ):
        create_response = await client.post(
            "/api/tasks",
            json={"user_query": "resume me", "engine": "auto"},
        )
        task_id = create_response.json()["task_id"]

        await _set_task_status(task_id, TaskStatus.RUNNING)
        await _set_task_status(task_id, TaskStatus.PAUSED)

        resume_response = await client.post(f"/api/tasks/{task_id}/resume")
        assert resume_response.status_code == 200
        assert resume_response.json()["status"] == "running"
        resume_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_pause_invalid_status_returns_409(client: AsyncClient) -> None:
    with patch("workflows.client.WorkflowScheduler.schedule_task", new=AsyncMock()):
        create_response = await client.post(
            "/api/tasks",
            json={"user_query": "invalid pause", "engine": "auto"},
        )
        task_id = create_response.json()["task_id"]

        pause_response = await client.post(f"/api/tasks/{task_id}/pause")
        assert pause_response.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pause_compensates_workflow_when_db_persist_fails() -> None:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with (
                patch(
                    "workflows.client.WorkflowScheduler.schedule_task",
                    new=AsyncMock(),
                ),
                patch(
                    "workflows.client.WorkflowScheduler.pause_task",
                    new=AsyncMock(),
                ) as pause_mock,
                patch(
                    "workflows.client.WorkflowScheduler.resume_task",
                    new=AsyncMock(),
                ) as resume_mock,
                patch(
                    "api.services.task_service.TaskService._persist_task_status",
                    new=AsyncMock(side_effect=RuntimeError("db unavailable")),
                ),
            ):
                create_response = await client.post(
                    "/api/tasks",
                    json={"user_query": "pause persist fail", "engine": "auto"},
                )
                task_id = create_response.json()["task_id"]
                await _set_task_status(task_id, TaskStatus.RUNNING)

                pause_response = await client.post(f"/api/tasks/{task_id}/pause")

    assert pause_response.status_code == 500
    pause_mock.assert_awaited_once()
    resume_mock.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resume_compensates_workflow_when_db_persist_fails() -> None:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with (
                patch(
                    "workflows.client.WorkflowScheduler.schedule_task",
                    new=AsyncMock(),
                ),
                patch(
                    "workflows.client.WorkflowScheduler.resume_task",
                    new=AsyncMock(),
                ) as resume_mock,
                patch(
                    "workflows.client.WorkflowScheduler.pause_task",
                    new=AsyncMock(),
                ) as pause_mock,
                patch(
                    "api.services.task_service.TaskService._persist_task_status",
                    new=AsyncMock(side_effect=RuntimeError("db unavailable")),
                ),
            ):
                create_response = await client.post(
                    "/api/tasks",
                    json={"user_query": "resume persist fail", "engine": "auto"},
                )
                task_id = create_response.json()["task_id"]
                await _set_task_status(task_id, TaskStatus.RUNNING)
                await _set_task_status(task_id, TaskStatus.PAUSED)

                resume_response = await client.post(f"/api/tasks/{task_id}/resume")

    assert resume_response.status_code == 500
    resume_mock.assert_awaited_once()
    pause_mock.assert_awaited_once()
