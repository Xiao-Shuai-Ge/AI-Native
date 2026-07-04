"""Ollama LLM adapter using OpenAI-compatible endpoint."""

from __future__ import annotations

import httpx

from llm.openai_compatible import OpenAICompatibleClient
from llm.protocol import LLMCapabilities


def create_ollama_client(
    *,
    base_url: str,
    model: str,
    http_client: httpx.AsyncClient | None = None,
) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        provider="ollama",
        model=model,
        base_url=base_url,
        api_key=None,
        capabilities=LLMCapabilities(
            supports_streaming=False,
            supports_tools=False,
            supports_structured_output=True,
            max_context_tokens=32768,
        ),
        http_client=http_client,
    )
