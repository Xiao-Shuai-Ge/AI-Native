"""Resilience tests for timeout and retry behavior (via litellm)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from litellm.exceptions import AuthenticationError, RateLimitError
from tests.llm_helpers import fake_litellm_response

from llm.adapters.openai_adapter import create_openai_client
from llm.errors import LLMConfigurationError, LLMTimeoutError
from llm.protocol import ChatMessage, ChatRole
from llm.resilient import ResilientLLMClient


@pytest.mark.asyncio
async def test_resilient_client_raises_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_acompletion(**_kwargs: object) -> object:
        await asyncio.sleep(0.2)
        return fake_litellm_response("late")

    monkeypatch.setattr("llm.litellm_support.litellm.acompletion", slow_acompletion)
    inner = create_openai_client(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    client = ResilientLLMClient(inner, default_timeout=0.05, max_retries=0)

    with pytest.raises(LLMTimeoutError):
        await client.chat(
            [ChatMessage(role=ChatRole.USER, content="hello")],
            timeout=0.05,
            task_id="task-timeout",
        )


@pytest.mark.asyncio
async def test_resilient_client_retries_once_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"count": 0}
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request, text="rate limited")
    rate_limit_error = RateLimitError(
        message="rate limited", llm_provider="openai", model="gpt-4o-mini", response=response
    )

    async def handler(**_kwargs: object) -> object:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise rate_limit_error
        return fake_litellm_response("recovered")

    monkeypatch.setattr("llm.litellm_support.litellm.acompletion", handler)
    inner = create_openai_client(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    client = ResilientLLMClient(inner, default_timeout=5.0, max_retries=1)

    response_out = await client.chat(
        [ChatMessage(role=ChatRole.USER, content="hello")],
        task_id="task-retry",
    )
    assert response_out.content == "recovered"
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_resilient_client_does_not_retry_on_authentication_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = {"count": 0}
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(401, request=request, text="unauthorized")
    auth_error = AuthenticationError(
        message="unauthorized", llm_provider="openai", model="gpt-4o-mini", response=response
    )

    async def handler(**_kwargs: object) -> object:
        attempts["count"] += 1
        raise auth_error

    monkeypatch.setattr("llm.litellm_support.litellm.acompletion", handler)
    inner = create_openai_client(
        api_key="bad-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    client = ResilientLLMClient(inner, default_timeout=5.0, max_retries=1)

    with pytest.raises(LLMConfigurationError):
        await client.chat([ChatMessage(role=ChatRole.USER, content="hello")])

    assert attempts["count"] == 1
