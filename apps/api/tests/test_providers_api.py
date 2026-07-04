"""Providers API tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.config import Settings, get_settings
from api.main import app
from llm.fake import FakeLLMClient


@pytest.fixture
async def client() -> AsyncClient:
    fake = FakeLLMClient(provider="fake", model="fake-model")
    test_settings = Settings.model_validate(
        {
            "llm_provider": "deepseek",
            "deepseek_api_key": "test-key",
        }
    )

    def override_settings() -> Settings:
        return test_settings

    app.dependency_overrides[get_settings] = override_settings

    from api.routes import providers as providers_module

    original_factory = providers_module.create_llm_client

    def override_create_llm_client(_settings: Settings) -> FakeLLMClient:
        return fake

    providers_module.create_llm_client = override_create_llm_client  # type: ignore[assignment]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    providers_module.create_llm_client = original_factory  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_providers_returns_current_provider_info(client: AsyncClient) -> None:
    response = await client.get("/api/providers")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fake"
    assert body["model"] == "fake-model"
    assert body["capabilities"]["supports_structured_output"] is True
