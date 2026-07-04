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
    with patch("api.services.task_service.MinimalTaskRunner.run", new=AsyncMock()):
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
async def test_list_tasks_returns_created_task(client: AsyncClient) -> None:
    with patch("api.services.task_service.MinimalTaskRunner.run", new=AsyncMock()):
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


@pytest.mark.asyncio
async def test_dapr_subscribe_endpoint(client: AsyncClient) -> None:
    response = await client.get("/dapr/subscribe")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["topic"] == "agent.task.events"
