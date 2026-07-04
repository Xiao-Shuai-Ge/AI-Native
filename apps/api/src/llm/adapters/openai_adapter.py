"""OpenAI LLM adapter."""

from __future__ import annotations

import httpx

from llm.openai_compatible import OpenAICompatibleClient
from llm.protocol import LLMCapabilities


def create_openai_client(
    *,
    api_key: str,
    base_url: str,
    model: str,
    http_client: httpx.AsyncClient | None = None,
) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        provider="openai",
        model=model,
        base_url=base_url,
        api_key=api_key,
        capabilities=LLMCapabilities(
            supports_streaming=False,
            supports_tools=False,
            supports_structured_output=True,
            max_context_tokens=128000,
        ),
        http_client=http_client,
    )
