"""SSE task events API tests."""

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


@pytest.mark.asyncio
async def test_task_events_stream_returns_snapshot_for_existing_task(
    client: AsyncClient,
) -> None:
    task_id = uuid4()
    task_payload = {
        "task_id": task_id,
        "status": "succeeded",
        "audit_events": [],
    }
    with patch(
        "api.routes.tasks._task_service",
    ) as service_factory:
        service = AsyncMock()
        service.get_task = AsyncMock(return_value=task_payload)
        service_factory.return_value = service

        async with client.stream("GET", f"/api/tasks/{task_id}/events") as response:
            assert response.status_code == 200
            body = ""
            async for chunk in response.aiter_text():
                body += chunk
                if "event: close" in body:
                    break

    assert "event: snapshot" in body
    assert str(task_id) in body
    assert "event: close" in body


@pytest.mark.asyncio
async def test_task_events_stream_reports_missing_task(client: AsyncClient) -> None:
    missing_id = uuid4()
    async with client.stream("GET", f"/api/tasks/{missing_id}/events") as response:
        body = ""
        async for chunk in response.aiter_text():
            body += chunk
            if "event: error" in body:
                break

    assert "task not found" in body
