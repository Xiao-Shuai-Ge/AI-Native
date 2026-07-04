"""Contract tests for all LLM provider adapters."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel
from tests.llm_helpers import anthropic_chat_payload, openai_chat_payload

from llm.adapters.anthropic import AnthropicClient
from llm.adapters.deepseek import create_deepseek_client
from llm.adapters.ollama import create_ollama_client
from llm.adapters.openai_adapter import create_openai_client
from llm.fake import FakeLLMClient
from llm.protocol import ChatMessage, ChatRole


class SampleOutput(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_fake_client_supports_chat_and_structured() -> None:
    client = FakeLLMClient()
    response = await client.chat(
        [ChatMessage(role=ChatRole.USER, content="hello")],
        timeout=5.0,
    )
    assert response.content == "fake response"

    structured = await FakeLLMClient(
        structured_handler=lambda _messages, schema: schema.model_validate({"answer": "ok"})
    ).chat_structured(
        [ChatMessage(role=ChatRole.USER, content="hello")],
        SampleOutput,
        timeout=5.0,
    )
    assert structured.answer == "ok"


@pytest.mark.parametrize(
    ("factory", "url", "request_model"),
    [
        (
            lambda transport: create_deepseek_client(
                api_key="test-key",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                http_client=httpx.AsyncClient(transport=transport),
            ),
            "https://api.deepseek.com/v1/chat/completions",
            "deepseek-chat",
        ),
        (
            lambda transport: create_ollama_client(
                base_url="http://localhost:11434/v1",
                model="qwen3:8b",
                http_client=httpx.AsyncClient(transport=transport),
            ),
            "http://localhost:11434/v1/chat/completions",
            "qwen3:8b",
        ),
        (
            lambda transport: create_openai_client(
                api_key="test-key",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                http_client=httpx.AsyncClient(transport=transport),
            ),
            "https://api.openai.com/v1/chat/completions",
            "gpt-4o-mini",
        ),
    ],
)
@pytest.mark.asyncio
async def test_openai_compatible_adapters_contract(
    factory: Any,
    url: str,
    request_model: str,
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json=openai_chat_payload("hello world", model=request_model),
        )

    transport = httpx.MockTransport(handler)
    client = factory(transport)
    response = await client.chat(
        [ChatMessage(role=ChatRole.USER, content="hello")],
        timeout=5.0,
    )

    assert captured["url"] == url
    assert captured["json"]["model"] == request_model
    assert response.content == "hello world"
    assert response.usage is not None
    assert response.usage.total_tokens == 36
    assert client.provider_info.capabilities.supports_structured_output is True


@pytest.mark.asyncio
async def test_openai_compatible_structured_output_parses_schema() -> None:
    payload = SampleOutput(answer="42")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=openai_chat_payload(payload.model_dump_json()),
        )

    transport = httpx.MockTransport(handler)
    client = create_openai_client(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        http_client=httpx.AsyncClient(transport=transport),
    )
    result = await client.chat_structured(
        [ChatMessage(role=ChatRole.USER, content="answer")],
        SampleOutput,
        timeout=5.0,
    )
    assert result.answer == "42"


@pytest.mark.asyncio
async def test_anthropic_adapter_contract() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json=anthropic_chat_payload("anthropic hello", model="claude-test"),
        )

    transport = httpx.MockTransport(handler)
    client = AnthropicClient(
        api_key="test-key",
        model="claude-test",
        http_client=httpx.AsyncClient(transport=transport),
    )
    response = await client.chat(
        [
            ChatMessage(role=ChatRole.SYSTEM, content="system"),
            ChatMessage(role=ChatRole.USER, content="hello"),
        ],
        timeout=5.0,
    )

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["json"]["system"] == "system"
    assert response.content == "anthropic hello"
    assert client.provider_info.provider == "anthropic"
