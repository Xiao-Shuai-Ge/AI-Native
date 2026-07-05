"""Settings API tests."""

from unittest.mock import AsyncMock, patch

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
async def test_get_settings_returns_defaults(client: AsyncClient) -> None:
    with patch(
        "persistence.dapr_client.DaprHttpClient.get_state",
        new=AsyncMock(return_value=None),
    ):
        response = await client.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert "llm" in body
    assert "agents" in body
    assert set(body["agents"]) == {"researcher", "analyst", "writer"}
    assert body["agents"]["writer"]["role"] == "技术撰稿人"


@pytest.mark.asyncio
async def test_put_settings_persists_overrides(client: AsyncClient) -> None:
    saved: dict[str, object] = {}

    async def fake_save_state(key: str, value: dict[str, object]) -> None:
        saved["key"] = key
        saved["value"] = value

    with (
        patch(
            "persistence.dapr_client.DaprHttpClient.get_state",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "persistence.dapr_client.DaprHttpClient.save_state",
            new=AsyncMock(side_effect=fake_save_state),
        ),
    ):
        response = await client.put(
            "/api/settings",
            json={
                "llm": {"provider": "ollama", "temperature": 0.2, "max_tokens": 2048},
                "agents": {
                    "writer": {
                        "role": "Writer",
                        "goal": "Write reports",
                        "backstory": "Experienced writer",
                        "instructions": "Use Markdown",
                        "version": "v2",
                    }
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["provider"] == "ollama"
    assert body["agents"]["writer"]["version"] == "v2"
    assert saved["key"] == "settings:runtime"


@pytest.mark.asyncio
async def test_put_settings_rejects_unknown_agent(client: AsyncClient) -> None:
    with patch(
        "persistence.dapr_client.DaprHttpClient.get_state",
        new=AsyncMock(return_value=None),
    ):
        response = await client.put(
            "/api/settings",
            json={
                "agents": {
                    "planner": {
                        "role": "Planner",
                        "goal": "Plan",
                        "backstory": "Plans",
                        "instructions": "Plan tasks",
                    }
                }
            },
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_put_settings_rejects_invalid_provider(client: AsyncClient) -> None:
    with patch(
        "persistence.dapr_client.DaprHttpClient.get_state",
        new=AsyncMock(return_value=None),
    ):
        response = await client.put(
            "/api/settings",
            json={"llm": {"provider": "invalid-vendor", "temperature": 0.7, "max_tokens": 4096}},
        )

    assert response.status_code == 422
