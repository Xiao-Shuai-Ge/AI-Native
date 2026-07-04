"""Dev writer API tests."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from agents.schemas import WriterSummary
from api.config import Settings, get_settings
from api.main import app
from llm.fake import FakeLLMClient


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    return FakeLLMClient(
        provider="fake",
        model="fake-model",
        structured_handler=lambda _messages, schema: schema.model_validate(
            {
                "title": "Test Topic",
                "summary": "This is a test summary.",
                "markdown": "# Test Topic\n\nThis is a test summary.",
            }
        ),
    )


@pytest.fixture
async def client(fake_llm_client: FakeLLMClient) -> AsyncClient:
    test_settings = Settings.model_validate(
        {
            "llm_provider": "deepseek",
            "deepseek_api_key": "test-key",
        }
    )

    def override_settings() -> Settings:
        return test_settings

    app.dependency_overrides[get_settings] = override_settings

    from api.routes import dev_writer as dev_writer_module

    original_factory = dev_writer_module.create_llm_client

    def override_create_llm_client(_settings: Settings) -> FakeLLMClient:
        return fake_llm_client

    dev_writer_module.create_llm_client = override_create_llm_client  # type: ignore[assignment]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    dev_writer_module.create_llm_client = original_factory  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_dev_writer_summarize_returns_structured_markdown(client: AsyncClient) -> None:
    task_id = uuid4()
    response = await client.post(
        "/api/dev/writer/summarize",
        json={"topic": "Dapr Workflow", "task_id": str(task_id)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == str(task_id)
    result = WriterSummary.model_validate(body["result"])
    assert result.markdown.startswith("#")
