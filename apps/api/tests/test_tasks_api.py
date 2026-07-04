"""Task API tests."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.fixture
async def client() -> AsyncClient:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_get_task(client: AsyncClient) -> None:
    with patch("workflows.client.WorkflowScheduler.schedule_task", new=AsyncMock()):
        create_response = await client.post(
            "/api/tasks",
            json={"user_query": "Explain Dapr state management", "engine": "auto"},
        )
        assert create_response.status_code == 201
        body = create_response.json()
        task_id = body["task_id"]
        assert body["status"] == "queued"
        assert body["workflow_id"] == f"wf-{task_id}"
        assert body["thread_id"] == task_id

        detail_response = await client.get(f"/api/tasks/{task_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["task_id"] == task_id
        assert detail["user_query"] == "Explain Dapr state management"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_task_marks_failed_when_workflow_schedule_fails(
    client: AsyncClient,
) -> None:
    task_id = uuid4()
    runtime_state = {"status": "failed", "current_step": "scheduling_failed"}
    with (
        patch(
            "workflows.client.WorkflowScheduler.schedule_task",
            new=AsyncMock(side_effect=RuntimeError("dapr unavailable")),
        ),
        patch("persistence.dapr_state.DaprStateStore.save_task_runtime_state", new=AsyncMock()),
        patch(
            "persistence.dapr_state.DaprStateStore.merge_task_runtime_state",
            new=AsyncMock(),
        ) as merge_state_mock,
        patch(
            "persistence.dapr_state.DaprStateStore.get_task_runtime_state",
            new=AsyncMock(return_value=runtime_state),
        ),
        patch("events.schemas.AgentTaskEventPublisher.publish", new=AsyncMock()),
    ):
        create_response = await client.post(
            "/api/tasks",
            json={
                "task_id": str(task_id),
                "user_query": "schedule should fail",
                "engine": "auto",
            },
        )
        detail_response = await client.get(f"/api/tasks/{task_id}")

    assert create_response.status_code == 503
    assert create_response.json()["detail"]["task_id"] == str(task_id)
    merge_state_mock.assert_awaited_once()

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "failed"
    assert detail["runtime_state"]["status"] == "failed"
    assert detail["runtime_state"]["current_step"] == "scheduling_failed"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_tasks_returns_created_task(client: AsyncClient) -> None:
    with patch("workflows.client.WorkflowScheduler.schedule_task", new=AsyncMock()):
        await client.post("/api/tasks", json={"user_query": "List me", "engine": "langgraph"})
        response = await client.get("/api/tasks")
        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) >= 1
        assert tasks[0]["user_query"] == "List me"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_preferences_roundtrip(client: AsyncClient) -> None:
    user_id = f"user-{uuid4()}"
    put_response = await client.put(
        f"/api/users/{user_id}/preferences",
        json={"preferences": {"language": "zh-CN", "report_format": "markdown"}},
    )
    assert put_response.status_code == 200

    get_response = await client.get(f"/api/users/{user_id}/preferences")
    assert get_response.status_code == 200
    assert get_response.json()["preferences"]["language"] == "zh-CN"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_explicit_zero_delay_overrides_default() -> None:
    from api.config import get_settings
    from api.deps import build_app_state
    from api.services.task_service import TaskService
    from orchestration.models import EngineChoice, TaskRequest

    state = build_app_state(get_settings())
    schedule_mock = AsyncMock()
    try:
        service = TaskService(
            state.session_factory,
            state.dapr_state,
            state.session_store,
            state.event_publisher,
            state.workflow_scheduler,
            default_delay_seconds=30.0,
        )
        service._workflow_scheduler.schedule_task = schedule_mock  # noqa: SLF001
        with (
            patch(
                "persistence.dapr_state.DaprStateStore.save_task_runtime_state",
                new=AsyncMock(),
            ),
            patch(
                "persistence.session_store.SessionStore.get_messages",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "persistence.session_store.SessionStore.append_message",
                new=AsyncMock(),
            ),
        ):
            await service.create_task(
                TaskRequest(
                    user_query="no delay",
                    engine=EngineChoice.AUTO,
                    delay_seconds=0.0,
                )
            )
            wf_input = schedule_mock.await_args.args[0]
            assert wf_input.delay_seconds == 0.0

            schedule_mock.reset_mock()
            await service.create_task(
                TaskRequest(user_query="default delay", engine=EngineChoice.AUTO)
            )
            wf_input_default = schedule_mock.await_args.args[0]
            assert wf_input_default.delay_seconds == 30.0
    finally:
        state.workflow_scheduler.close()
        await state.engine.dispose()


@pytest.mark.asyncio
async def test_dapr_subscribe_endpoint(client: AsyncClient) -> None:
    response = await client.get("/dapr/subscribe")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["topic"] == "agent.task.events"
