"""Resilience tests for timeout and retry behavior."""

from __future__ import annotations

import httpx
import pytest
from tests.llm_helpers import openai_chat_payload

from llm.adapters.openai_adapter import create_openai_client
from llm.errors import LLMTimeoutError, LLMUnavailableError
from llm.protocol import ChatMessage, ChatRole
from llm.resilient import ResilientLLMClient


@pytest.mark.asyncio
async def test_resilient_client_raises_timeout_error() -> None:
    async def slow_handler(_request: httpx.Request) -> httpx.Response:
        import asyncio

        await asyncio.sleep(0.2)
        return httpx.Response(200, json=openai_chat_payload("late"))

    transport = httpx.MockTransport(slow_handler)
    inner = create_openai_client(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        http_client=httpx.AsyncClient(transport=transport),
    )
    client = ResilientLLMClient(inner, default_timeout=0.05, max_retries=0)

    with pytest.raises(LLMTimeoutError):
        await client.chat(
            [ChatMessage(role=ChatRole.USER, content="hello")],
            timeout=0.05,
            task_id="task-timeout",
        )


@pytest.mark.asyncio
async def test_resilient_client_retries_once_on_503() -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, text="upstream unavailable")
        return httpx.Response(200, json=openai_chat_payload("recovered"))

    transport = httpx.MockTransport(handler)
    inner = create_openai_client(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        http_client=httpx.AsyncClient(transport=transport),
    )
    client = ResilientLLMClient(inner, default_timeout=5.0, max_retries=1)

    response = await client.chat(
        [ChatMessage(role=ChatRole.USER, content="hello")],
        task_id="task-retry",
    )
    assert response.content == "recovered"
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_resilient_client_does_not_retry_on_401() -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(401, text="unauthorized")

    transport = httpx.MockTransport(handler)
    inner = create_openai_client(
        api_key="bad-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        http_client=httpx.AsyncClient(transport=transport),
    )
    client = ResilientLLMClient(inner, default_timeout=5.0, max_retries=1)

    with pytest.raises(LLMUnavailableError):
        await client.chat([ChatMessage(role=ChatRole.USER, content="hello")])

    assert attempts["count"] == 1
