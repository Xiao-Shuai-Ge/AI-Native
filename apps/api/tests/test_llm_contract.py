"""Contract tests for all LLM provider adapters (via litellm)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel
from tests.llm_helpers import fake_litellm_response

from llm.adapters.anthropic import AnthropicClient
from llm.adapters.deepseek import create_deepseek_client
from llm.adapters.ollama import create_ollama_client
from llm.adapters.openai_adapter import create_openai_client
from llm.fake import FakeLLMClient
from llm.protocol import ChatMessage, ChatRole, ToolDefinition


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
    ("factory", "expected_model_prefix", "request_model"),
    [
        (
            lambda: create_deepseek_client(
                api_key="test-key",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
            ),
            "openai/",
            "deepseek-chat",
        ),
        (
            lambda: create_ollama_client(
                base_url="http://localhost:11434/v1",
                model="qwen3:8b",
            ),
            "openai/",
            "qwen3:8b",
        ),
        (
            lambda: create_openai_client(
                api_key="test-key",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
            ),
            "openai/",
            "gpt-4o-mini",
        ),
    ],
)
@pytest.mark.asyncio
async def test_openai_compatible_adapters_contract(
    factory: Any,
    expected_model_prefix: str,
    request_model: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_acompletion = AsyncMock(
        return_value=fake_litellm_response("hello world", model=request_model)
    )
    monkeypatch.setattr("llm.litellm_support.litellm.acompletion", mock_acompletion)

    client = factory()
    response = await client.chat(
        [ChatMessage(role=ChatRole.USER, content="hello")],
        timeout=5.0,
    )

    call_kwargs = mock_acompletion.call_args.kwargs
    assert call_kwargs["model"] == f"{expected_model_prefix}{request_model}"
    assert response.content == "hello world"
    assert response.usage is not None
    assert response.usage.total_tokens == 36
    assert client.provider_info.capabilities.supports_structured_output is True
    assert client.provider_info.capabilities.supports_tools is True


@pytest.mark.asyncio
async def test_openai_compatible_structured_output_parses_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = SampleOutput(answer="42")
    mock_acompletion = AsyncMock(return_value=fake_litellm_response(payload.model_dump_json()))
    monkeypatch.setattr("llm.litellm_support.litellm.acompletion", mock_acompletion)

    client = create_openai_client(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    result = await client.chat_structured(
        [ChatMessage(role=ChatRole.USER, content="answer")],
        SampleOutput,
        timeout=5.0,
    )
    assert result.answer == "42"
    call_kwargs = mock_acompletion.call_args.kwargs
    assert call_kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_openai_compatible_adapter_forwards_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_acompletion = AsyncMock(
        return_value=fake_litellm_response(
            "",
            tool_calls=[
                {"id": "call-1", "name": "calculator", "arguments": '{"expression": "1+1"}'}
            ],
            finish_reason="tool_calls",
        )
    )
    monkeypatch.setattr("llm.litellm_support.litellm.acompletion", mock_acompletion)

    client = create_openai_client(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    tools = [ToolDefinition(name="calculator", description="Evaluate math", parameters={})]
    response = await client.chat(
        [ChatMessage(role=ChatRole.USER, content="what is 1+1")],
        timeout=5.0,
        tools=tools,
    )

    assert response.tool_calls is not None
    assert response.tool_calls[0].name == "calculator"
    assert response.tool_calls[0].arguments == {"expression": "1+1"}
    call_kwargs = mock_acompletion.call_args.kwargs
    assert call_kwargs["tools"][0]["function"]["name"] == "calculator"
    assert call_kwargs["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_anthropic_adapter_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_acompletion = AsyncMock(
        return_value=fake_litellm_response("anthropic hello", model="claude-test")
    )
    monkeypatch.setattr("llm.litellm_support.litellm.acompletion", mock_acompletion)

    client = AnthropicClient(api_key="test-key", model="claude-test")
    response = await client.chat(
        [
            ChatMessage(role=ChatRole.SYSTEM, content="system"),
            ChatMessage(role=ChatRole.USER, content="hello"),
        ],
        timeout=5.0,
    )

    call_kwargs = mock_acompletion.call_args.kwargs
    assert call_kwargs["model"] == "claude-test"
    assert call_kwargs["api_key"] == "test-key"
    assert response.content == "anthropic hello"
    assert client.provider_info.provider == "anthropic"
    assert client.provider_info.capabilities.supports_tools is True
