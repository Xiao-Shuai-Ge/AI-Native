"""Error handling tests for LLM adapters (via litellm)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from litellm.exceptions import AuthenticationError
from pydantic import BaseModel
from tests.llm_helpers import fake_litellm_response

from api.config import Settings
from llm.adapters.openai_adapter import create_openai_client
from llm.errors import LLMConfigurationError, LLMParseError, LLMUnavailableError
from llm.factory import create_llm_client
from llm.protocol import ChatMessage, ChatRole


class SampleOutput(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_unavailable_provider_raises_llm_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(401, request=request, text="invalid api key")
    error = AuthenticationError(
        message="invalid api key",
        llm_provider="openai",
        model="gpt-4o-mini",
        response=response,
    )
    mock_acompletion = AsyncMock(side_effect=error)
    monkeypatch.setattr("llm.litellm_support.litellm.acompletion", mock_acompletion)

    client = create_openai_client(
        api_key="bad-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )

    with pytest.raises(LLMConfigurationError):
        await client.chat([ChatMessage(role=ChatRole.USER, content="hello")], timeout=5.0)


@pytest.mark.asyncio
async def test_invalid_structured_output_raises_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_acompletion = AsyncMock(return_value=fake_litellm_response('{"wrong":"field"}'))
    monkeypatch.setattr("llm.litellm_support.litellm.acompletion", mock_acompletion)

    client = create_openai_client(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )

    with pytest.raises(LLMParseError):
        await client.chat_structured(
            [ChatMessage(role=ChatRole.USER, content="hello")],
            SampleOutput,
            timeout=5.0,
        )


def test_factory_requires_api_key_for_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    # `Settings` still merges in the process environment/`.env` file even
    # when constructed explicitly, so a real DEEPSEEK_API_KEY in the
    # developer's `.env` would otherwise mask the empty value under test.
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_provider="deepseek",
        deepseek_api_key="",
    )
    with pytest.raises(LLMConfigurationError):
        create_llm_client(settings)


@pytest.mark.asyncio
async def test_no_choices_raises_llm_unavailable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    mock_acompletion = AsyncMock(return_value=SimpleNamespace(choices=[], usage=None, model="x"))
    monkeypatch.setattr("llm.litellm_support.litellm.acompletion", mock_acompletion)

    client = create_openai_client(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )

    with pytest.raises(LLMUnavailableError):
        await client.chat([ChatMessage(role=ChatRole.USER, content="hello")], timeout=5.0)
